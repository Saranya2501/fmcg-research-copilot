from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from integrations import agent_bridge as bridge
from integrations import tracing
from integrations.external_p2 import load_p2

GATE={'use_case':'UC1','in_scope':True,'companies':['HUL'],'metrics':['revenue'],'fiscal_years':['FY24'],'resolved_question':'HUL revenue FY24?'}
PLAN={'subtasks':[{'id':'t1','company':'HUL','metric':'revenue','fiscal_year':'FY24','kind':'lookup','question':'HUL revenue FY24?'}],
      'combine':'single_answer','combine_instruction':'Answer'}
QUERY={'queries':['HUL FY24 revenue'],'filters':{'company':'HUL','fiscal_year':'FY24'}}
ANALYST={'values':[{'label':'revenue','value':100,'unit':'Rs crore','fiscal_year':'FY24','chunk_id':'c1','quote':'Revenue 100'}],'missing':[]}
WRITER={'answer':'HUL revenue was 100 crore [c1].','value':100,'unit':'Rs crore','fiscal_year':'FY24','citations':[{'chunk_id':'c1'}],'refused':False}
CRITIC={'verdict':'pass','issues':[]}
ROWS=[{'chunk_id':'c1','doc_id':'hul_fy24','company':'HUL','fiscal_year':'FY24','page':9,'text':'Revenue 100'}]


class ScriptedModel:
    def __init__(self, replies): self.replies=deepcopy(replies);self.calls=[];self.closed=False
    def chat(self,messages,**kwargs):
        self.calls.append((messages,kwargs))
        text=json.dumps(self.replies.pop(0))
        return SimpleNamespace(text=text,raw_text=text,usage={'prompt_tokens':8,'completion_tokens':2,'total_tokens':10},latency_s=0.01,cached=False)
    def close(self): self.closed=True


class LatestP4BridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'CHAT_HISTORY_DB':self.folder.name+'/chat.sqlite3','CHAT_BACKEND':'agent',
            'CHAT_CACHE_ENABLED':'true','LANGFUSE_TRACING_ENABLED':'false','AGENT_TOKEN_BUDGET':'6000'})
        self.env.start()
        self.no_trace=patch.object(tracing,'get_tracing_client',return_value=None)
        self.no_trace.start()
        self.retrieval_calls=[]
        def retrieve(**kwargs): self.retrieval_calls.append(kwargs);return deepcopy(ROWS)
        self.p3=SimpleNamespace(retrieve=retrieve,get_table=lambda **kwargs:{})

    def tearDown(self):
        self.no_trace.stop();self.env.stop();self.folder.cleanup()

    def execute(self, model, history=None, config=None, filters=None):
        with patch.object(bridge,'missing_setup',return_value=[]),patch.object(bridge,'load_retrieval',return_value=self.p3),patch.object(bridge,'_make_client',return_value=model):
            return bridge.run_agent('HUL revenue FY24?',history or [],filters or {},config or bridge.configuration())

    def test_uses_supplied_runtime_without_changing_its_source(self):
        path=bridge.P4_ROOT/'integration/runtime.py'
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        model=ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,CRITIC])
        result=self.execute(model)
        self.assertEqual(result.status,'answered')
        self.assertTrue(result.cacheable)
        self.assertEqual(result.citations[0]['document'],'hul_fy24')
        self.assertEqual(result.citations[0]['page'],9)
        self.assertEqual(result.usage['total_tokens'],60)
        self.assertEqual(len(result.metrics['json_steps']),6)
        self.assertTrue(model.closed)
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_followup_history_and_context_reach_latest_p2_gatekeeper(self):
        history=[{'role':'user','content':'HUL revenue FY25?'},{'role':'assistant','content':'Previous answer',
                  'response':{'agent_context':{'companies':['HUL'],'metrics':['revenue'],'fiscal_years':['FY25'],'use_case':'UC1'}}}]
        model=ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,CRITIC])
        result=self.execute(model,history)
        self.assertEqual(result.agent_context['fiscal_years'],['FY24'])
        self.assertTrue(any(m['content']=='Previous answer' for m in model.calls[0][0]))
        self.assertIn('FY25',model.calls[0][0][-1]['content'])

    def test_saved_direct_conversation_continues_through_research(self):
        from streamlit.testing.v1 import AppTest

        session = app.create_user_session('Test User')
        conversation = app.create_conversation(user_session_id=session)
        with app.history_db() as db:
            db.execute("UPDATE conversations SET mode='chat' WHERE id=?", (conversation,))
        app.save_message(conversation, 'user', 'Previous question')
        app.save_message(conversation, 'assistant', 'Previous answer')
        model = ScriptedModel([GATE, PLAN, QUERY, ANALYST, WRITER, CRITIC])
        ui = AppTest.from_file(str(Path(app.__file__)))
        ui.query_params.update({'session': session, 'chat': conversation})
        with patch.dict(os.environ, {'CHAT_RETRIEVAL_ENABLED': 'false'}), patch.object(
            bridge, 'missing_setup', return_value=[]
        ), patch.object(bridge, 'load_retrieval', return_value=self.p3), patch.object(
            bridge, '_make_client', return_value=model
        ):
            ui.run()
            ui.chat_input[0].set_value(GATE['resolved_question']).run()

        self.assertFalse(ui.exception)
        messages = app.load_messages(conversation)
        self.assertEqual(messages[1]['content'], 'Previous answer')
        self.assertEqual(messages[-1]['response']['status'], 'answered')
        self.assertEqual(len(self.retrieval_calls), 1)

    def test_critic_can_reject_standalone_revenue_for_a_consolidated_lookup(self):
        question = "What was HUL's consolidated revenue in FY24?"
        standalone = {**ROWS[0], 'standalone_consolidated': 'standalone'}
        consolidated = {**ROWS[0], 'chunk_id': 'c2', 'page': 10, 'text': 'Revenue 120',
                        'standalone_consolidated': 'consolidated'}
        self.p3.retrieve = lambda **kwargs: [standalone, consolidated]
        gate = {**GATE, 'resolved_question': question}
        plan = {**PLAN, 'subtasks': [{**PLAN['subtasks'][0], 'question': question}]}
        critique = {'verdict': 'revise', 'issues': [{
            'claim': '100 crore', 'quote': '100 crore', 'correct': 'Consolidated revenue was 120 crore',
            'problem': 'answers_wrong_question', 'fix_owner': 'analyst',
            'instruction': 'Use consolidated FY24 revenue from c2.'}]}
        model = ScriptedModel([gate, plan, QUERY, ANALYST, WRITER, critique])

        result = self.execute(model)

        writer_prompt = model.calls[4][0][-1]['content']
        critic_prompt = model.calls[5][0][-1]['content']
        self.assertIn('Revenue 100', writer_prompt)
        self.assertNotIn('Revenue 120', writer_prompt)
        self.assertIn('Revenue 100', critic_prompt)
        self.assertIn('Revenue 120', critic_prompt)
        self.assertIn('p.9, standalone', critic_prompt)
        self.assertIn('p.10, consolidated', critic_prompt)
        self.assertEqual(result.status, 'partial')
        self.assertFalse(result.cacheable)
        self.assertNotIn(WRITER['answer'], result.answer)

    def test_partial_validation_is_partial_and_not_cached(self):
        critic={'verdict':'revise','issues':[{'claim':'100 crore','quote':'100 crore','correct':'100 crore','problem':'wrong_number',
            'fix_owner':'writer','instruction':'Recheck the claim.'}]}
        result=self.execute(ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,critic]))
        self.assertEqual(result.status,'partial')
        self.assertFalse(result.cacheable)
        self.assertNotIn('HUL revenue was',result.answer)
        self.assertIn('wrong number', result.answer)
        self.assertIn('Reviewer feedback: Recheck the claim.', result.limitations)

    def test_refusal_contract_is_normalized(self):
        gate={**GATE,'in_scope':False,'refusal_reason':'advice_or_forecast','refusal_message':'No investment advice.'}
        result=self.execute(ScriptedModel([gate]))
        self.assertEqual(result.status,'refused')
        self.assertEqual(result.answer,'No investment advice.')
        self.assertFalse(self.retrieval_calls)

    def test_evaluation_bypasses_underlying_model_cache(self):
        model=ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,CRITIC])
        self.execute(model,config={**bridge.configuration(),'bypass_model_cache':True})
        self.assertTrue(all(k.get('use_cache') is False for _,k in model.calls))

    def test_budget_failure_is_not_reported_as_answered(self):
        model=ScriptedModel([])
        result=self.execute(model,config={**bridge.configuration(),'token_budget':1})
        self.assertEqual(result.status,'partial');self.assertFalse(result.cacheable)
        self.assertFalse(model.calls)

    def test_missing_data_does_not_call_the_model(self):
        with patch.object(bridge,'missing_setup',return_value=['parsed/all_chunks.jsonl']),patch.object(bridge,'_make_client') as make:
            result=bridge.run_agent('question',[],{},bridge.configuration())
        make.assert_not_called()
        self.assertTrue(result.metrics['setup_required'])

    def test_exact_cache_and_persisted_agent_context_use_latest_p4(self):
        model=ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,CRITIC])
        with patch.object(bridge,'missing_setup',return_value=[]),patch.object(bridge,'load_retrieval',return_value=self.p3),patch.object(bridge,'_make_client',return_value=model):
            first,second=app.create_conversation(),app.create_conversation()
            app.process_chat_turn('HUL revenue FY24?',first)
            app.process_chat_turn('HUL revenue FY24?',second)
        self.assertEqual(len(model.calls),6)
        saved=app.load_messages(second)[-1]
        self.assertEqual(saved['cache_status'],'hit')
        self.assertEqual(saved['response']['agent_context']['companies'],['HUL'])
        self.assertEqual(saved['response']['usage']['total_tokens'],0)
        self.assertEqual(saved['citations'][0]['page'],9)

    def test_flat_module_names_cannot_select_an_old_p2_package(self):
        with patch.dict(sys.modules,{'config':SimpleNamespace(PROMPT_VERSION='wrong-source')}):
            modules=load_p2(bridge.p2_path())
        self.assertEqual(modules['config'].PROMPT_VERSION,'agents-v10.2')
        self.assertTrue(Path(modules['agents'].__file__).is_relative_to(bridge.P4_ROOT))

    def test_missing_or_unknown_page_never_becomes_cacheable(self):
        raw={'status':'answered','answer':WRITER,'results':[],'critic':CRITIC,'missing':[]}
        result=bridge.normalize_response(raw,{}, {},{}, {})
        self.assertFalse(result.cacheable)
        self.assertEqual(result.status,'partial')

    def test_unverified_critic_pass_is_partial_and_not_cached(self):
        result = self.execute(ScriptedModel([
            GATE, PLAN, QUERY, ANALYST, WRITER, {**CRITIC, 'verified': False},
        ]))
        self.assertEqual(result.status, 'partial')
        self.assertFalse(result.successful)
        self.assertFalse(result.cacheable)
        self.assertIn('The critic could not independently verify this draft.', result.limitations)

    def test_runtime_calculator_is_traced_and_counted(self):
        analysis={**ANALYST,'calculation':{'expression':'revenue / 2','variables':{'revenue':'revenue'},'result_unit':'Rs crore'}}
        writer={**WRITER,'answer':'Calculated value: 50 crore [c1].','value':50}
        plan = {**PLAN, 'subtasks': [{**PLAN['subtasks'][0], 'kind': 'calculate'}]}
        result=self.execute(ScriptedModel([GATE,plan,QUERY,analysis,writer,CRITIC]))
        self.assertEqual(result.status,'answered')
        self.assertEqual(result.metrics['tool_calls'],2)
        self.assertEqual(result.results[-1]['value'],50)

    def test_unsupported_analyst_output_becomes_a_noncacheable_evidence_gap(self):
        from streamlit.testing.v1 import AppTest

        analyst = {
            'values': [{**ANALYST['values'][0], 'label': 'advertisement and promotion spends', 'value': 0.8}],
            'calculation': {
                'expression': 'spend / revenue * 100',
                'variables': {'spend': 'advertisement and promotion spends', 'revenue': 'revenue from operations'},
                'result_unit': '%',
            },
        }
        plan = {**PLAN, 'subtasks': [{**PLAN['subtasks'][0], 'kind': 'calculate'}]}
        model = ScriptedModel([GATE, plan, QUERY, analyst, analyst, analyst])
        with patch.object(bridge, 'missing_setup', return_value=[]), patch.object(
            bridge, 'load_retrieval', return_value=self.p3
        ), patch.object(bridge, '_make_client', return_value=model):
            ui = AppTest.from_file(str(Path(app.__file__))).run()
            ui.text_input[0].set_value('Test User')
            ui.button[0].click().run()
            ui.chat_input[0].set_value(GATE['resolved_question']).run()

        self.assertFalse(ui.exception)
        message = ui.session_state['messages'][-1]
        result = message['response']
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['cacheable'])
        self.assertEqual(len(model.calls), 6)
        self.assertEqual(result['metrics']['tool_calls'], 1)
        self.assertEqual([row['value'] for row in result['results']], [None])
        self.assertIn('could not verify an answer', message['content'])
        self.assertTrue(any('could not verify the required figures' in caption.value for caption in ui.caption))
        repair_prompt = model.calls[-1][0][-1]['content']
        self.assertIn('value 0.8', repair_prompt)
        self.assertIn("variable 'revenue'", repair_prompt)

    def test_missing_analyst_input_keeps_grounded_results_and_reports_the_gap(self):
        analyst = {**ANALYST, 'missing': ['advertisement and promotion spends']}
        model = ScriptedModel([GATE, PLAN, QUERY, analyst, WRITER, CRITIC])
        result = self.execute(model)

        self.assertEqual(result.status, 'partial')
        self.assertFalse(result.cacheable)
        self.assertIn('advertisement and promotion spends', result.limitations[0])
        self.assertEqual([row['value'] for row in result.results], [None, 100])
        self.assertIn('advertisement and promotion spends', model.calls[-2][0][-1]['content'])

    def test_advertising_lookup_selects_consolidated_expense_note(self):
        note = {**ROWS[0], 'chunk_id': 'expense-note', 'page': 200,
                'text': 'Advertising and promotion 6,489 4,907',
                'standalone_consolidated': 'consolidated'}
        standalone_note = {**note, 'chunk_id': 'standalone-note', 'page': 158,
                           'text': 'Advertising and promotion 6,380 4,859',
                           'standalone_consolidated': 'standalone'}
        distractors = [{**ROWS[0], 'chunk_id': f'distractor-{i}'} for i in range(5)]

        def retrieve(query, **kwargs):
            return [standalone_note, note] if query == 'advertising and promotion other expenses' else distractors

        self.p3.retrieve = retrieve
        question = "What were HUL's advertising expenses in FY24?"
        gate = {**GATE, 'resolved_question': question}
        plan = {**PLAN, 'subtasks': [{**PLAN['subtasks'][0], 'metric': 'advertising expenses', 'question': question}]}
        analyst = {'values': [{**ANALYST['values'][0], 'label': 'advertising and promotion', 'value': 6489,
                               'chunk_id': 'expense-note', 'quote': 'Advertising and promotion 6,489'}]}
        writer = {**WRITER, 'answer': 'HUL reported 6489 crore [expense-note].', 'value': 6489,
                  'citations': [{'chunk_id': 'expense-note'}]}
        model = ScriptedModel([gate, plan, QUERY, analyst, writer, CRITIC])
        result = self.execute(model)

        self.assertEqual(result.status, 'answered')
        self.assertEqual(result.citations[0]['page'], 200)
        self.assertEqual(result.results[0]['chunk_ids'], ['expense-note'])
        self.assertEqual(result.metrics['tool_calls'], 1)
        self.assertIn('[E1] (HUL, FY24, hul_fy24 p.200, consolidated)', model.calls[3][0][-1]['content'])
        self.assertNotIn('distractor-0', model.calls[3][0][-1]['content'])
        self.assertNotIn('standalone-note', model.calls[3][0][-1]['content'])

    def test_streamlit_research_greeting_skips_planner(self):
        from streamlit.testing.v1 import AppTest

        reply = "Hello! What would you like to research?"
        model = ScriptedModel([{**GATE, "use_case": "UC7", "in_scope": False,
                                "refusal_reason": "out_of_scope", "refusal_message": reply,
                                "companies": [], "metrics": [], "fiscal_years": [],
                                "resolved_question": "hi"}])
        with patch.object(bridge, "missing_setup", return_value=[]), patch.object(
            bridge, "load_retrieval", return_value=self.p3
        ), patch.object(bridge, "_make_client", return_value=model):
            ui = AppTest.from_file(str(Path(app.__file__))).run()
            ui.text_input[0].set_value("Test User")
            ui.button[0].click().run()
            ui.chat_input[0].set_value("hi").run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.session_state["messages"][-1]["content"], reply)
            self.assertEqual(len(model.calls), 1)
            self.assertFalse(self.retrieval_calls)

    def test_streamlit_shows_sources_without_technical_labels(self):
        from streamlit.testing.v1 import AppTest
        model=ScriptedModel([GATE,PLAN,QUERY,ANALYST,WRITER,CRITIC])
        with patch.object(bridge,'missing_setup',return_value=[]),patch.object(bridge,'load_retrieval',return_value=self.p3),\
             patch.object(bridge,'_make_client',return_value=model),\
             patch.object(tracing,'trace_identity',return_value=('ui-trace','https://example.test/ui-trace')):
            ui=AppTest.from_file(str(Path(app.__file__))).run()
            ui.text_input[0].set_value("Test User")
            ui.button[0].click().run()
            ui.chat_input[0].set_value('HUL revenue FY24?').run()
            self.assertFalse(ui.exception)
            self.assertTrue(any(e.label=='Sources' for e in ui.expander))
            self.assertEqual(len(ui.get('link_button')),0)
            ui.sidebar.button[0].click().run()
            ui.chat_input[0].set_value('HUL revenue FY24?').run()
            self.assertEqual(len(model.calls),6)
            self.assertFalse(any(c.value=='Cached response' for c in ui.caption))
            self.assertTrue(any(e.label=='Sources' for e in ui.expander))
            self.assertEqual(ui.session_state['messages'][-1]['response']['agent_context']['companies'],['HUL'])


if __name__=='__main__': unittest.main()
