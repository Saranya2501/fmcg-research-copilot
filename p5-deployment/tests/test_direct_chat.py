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


class Model:
    def __init__(self):
        self.calls=[];self.closed=False
        self._client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=self.create)))

    def create(self, **kwargs):
        if not kwargs.get('stream'):
            return None
        chunks=[SimpleNamespace(usage=None, choices=[SimpleNamespace(
            delta=SimpleNamespace(content=text), finish_reason=finish)])
            for text,finish in [('Hello',None),(' from the model.',None),(None,'stop')]]
        chunks.append(SimpleNamespace(choices=[], usage=SimpleNamespace(
            prompt_tokens=10,completion_tokens=5,total_tokens=15)))
        class Stream:
            def __iter__(self): return iter(chunks)
            def close(self): pass
        return Stream()
    def chat(self,messages,**kwargs):
        self.calls.append((messages,kwargs))
        self._client.chat.completions.create(messages=messages)
        return SimpleNamespace(text='Hello from the model.',usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},
                               cached=False,finish_reason='stop')
    def close(self): self.closed=True


class DirectChatTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'CHAT_HISTORY_DB':self.folder.name+'/chat.sqlite3',
            'CHAT_BACKEND':'agent','P3_RAG_PATH':self.folder.name+'/missing-corpus','LLM_BASE_URL':'https://provider.invalid/v1',
            'LLM_API_KEY':'test-only','LLM_MODEL':'test-model','LLM_TLS_CA_CERT':'','CHAT_CACHE_ENABLED':'true'})
        self.env.start()
        self.no_trace=patch.object(tracing,'get_tracing_client',return_value=None)
        self.no_trace.start()

    def tearDown(self): self.no_trace.stop();self.env.stop();self.folder.cleanup()

    def test_direct_call_skips_retrieval_and_preserves_recent_history(self):
        model=Model()
        with patch.object(bridge,'_make_client',return_value=model),\
             patch.object(bridge,'missing_setup',side_effect=AssertionError('Research setup must not run')),\
             patch.object(bridge,'load_retrieval',side_effect=AssertionError('Retrieval must not run')):
            result=bridge.run_direct_chat('Hello',[{'role':'user','content':'My name is Sam.'}],bridge.configuration(direct=True))
        self.assertEqual(result.answer,'Hello from the model.')
        self.assertEqual(result.usage['total_tokens'],15)
        self.assertFalse(result.metrics['retrieval_used'])
        self.assertEqual(result.citations,[])
        self.assertEqual(model.calls[0][0][-2]['content'],'My name is Sam.')
        self.assertNotIn('response_format',model.calls[0][1])
        self.assertTrue(model.closed)

    def test_cache_and_conversation_modes_are_separate(self):
        model=Model()
        first,second=app.create_conversation('chat'),app.create_conversation('chat')
        with patch.object(bridge,'_make_client',return_value=model),patch.object(bridge,'load_retrieval',side_effect=AssertionError):
            app.process_chat_turn('Hello',first,mode='chat')
            app.process_chat_turn('Hello',second,mode='chat')
        self.assertEqual(len(model.calls),1)
        saved=app.load_messages(second)[-1]
        self.assertEqual(saved['cache_status'],'hit')
        self.assertEqual(saved['response']['metrics']['mode'],'chat')
        self.assertEqual(saved['response']['usage']['total_tokens'],0)
        self.assertNotEqual(bridge.configuration()['backend'],bridge.configuration(direct=True)['backend'])

    def test_fresh_chat_streams_and_cached_chat_returns_immediately(self):
        model=Model()
        first,second=app.create_conversation('chat'),app.create_conversation('chat')
        updates=[]
        cached_updates=[]
        with patch.object(bridge,'_make_client',return_value=model):
            answer=app.process_chat_turn('Hello',first,mode='chat',on_text=updates.append)
            cached=app.process_chat_turn('Hello',second,mode='chat',on_text=cached_updates.append)
        self.assertEqual(answer,'Hello from the model.')
        self.assertEqual(cached,answer)
        self.assertEqual(len(model.calls),1)
        self.assertIn('Hello',updates)
        self.assertEqual(updates[-1],answer)
        self.assertEqual(cached_updates,[])
        self.assertEqual(app.load_messages(first)[-1]['cache_status'],'miss')
        self.assertEqual(app.load_messages(second)[-1]['cache_status'],'hit')

    def test_env_disables_retrieval_for_research_turns(self):
        model = Model()
        conversation = app.create_conversation('research')
        with patch.dict(os.environ, {'CHAT_RETRIEVAL_ENABLED': 'false'}), \
             patch.object(bridge, '_make_client', return_value=model), \
             patch.object(bridge, 'missing_setup', side_effect=AssertionError('No research setup')), \
             patch.object(bridge, 'load_retrieval', side_effect=AssertionError('No retrieval')):
            self.assertEqual(app.response_config()['backend'], 'chat')
            app.process_chat_turn('Hello', conversation)
        result = app.load_messages(conversation)[-1]['response']
        self.assertEqual(result['metrics']['mode'], 'chat')
        self.assertFalse(result['metrics']['retrieval_used'])
        self.assertEqual(result['citations'], [])

    def test_invalid_retrieval_setting_is_rejected(self):
        with patch.dict(os.environ, {'CHAT_RETRIEVAL_ENABLED': 'invalid'}):
            with self.assertRaisesRegex(ValueError, 'CHAT_RETRIEVAL_ENABLED'):
                app.response_config()

    def test_missing_key_is_independent_of_missing_corpus(self):
        with patch.dict(os.environ,{'LLM_API_KEY':''}),patch.object(bridge,'_make_client') as make:
            result=bridge.run_direct_chat('Hello',[],bridge.configuration(direct=True))
        make.assert_not_called()
        self.assertIn('LLM_API_KEY',result.metrics['missing_setup'])
        self.assertNotIn('parsed/all_chunks.jsonl',result.metrics['missing_setup'])

    def test_provider_error_is_controlled_and_not_cacheable(self):
        model=Model()
        model.chat=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('Do not display sensitive details'))
        with patch.object(bridge,'_make_client',return_value=model):
            result=bridge.run_direct_chat('Hello',[],bridge.configuration(direct=True))
        self.assertFalse(result.successful);self.assertFalse(result.cacheable)
        self.assertNotIn('sensitive',result.answer)

    def test_saved_direct_chat_and_new_research_chat(self):
        from streamlit.testing.v1 import AppTest
        model=Model()
        with patch.dict(os.environ, {'CHAT_RETRIEVAL_ENABLED': 'true'}), \
             patch('ui.chat.get_redis_client'), \
             patch.object(bridge,'_make_client',return_value=model):
            ui=AppTest.from_file(str(Path(app.__file__))).run()
            ui.text_input[0].set_value("Test User")
            ui.button[0].click().run()
            direct=app.create_conversation('chat', user_session_id=ui.session_state['user_session_id'])
            app.save_message(direct, 'user', 'Previous question')
            ui.run()
            ui.sidebar.button(key='history_'+direct).click().run()
            self.assertEqual(ui.session_state['active_conversation_id'], direct)
            self.assertFalse(any('Research setup' in w.value for w in ui.warning))
            ui.chat_input[0].set_value('Hello').run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.session_state['messages'][-1]['content'],'Hello from the model.')
            self.assertTrue(any(c.value=='Tokens · Input: 10 · Output: 5 · Total: 15' for c in ui.caption))
            ui.sidebar.button[0].click().run()
            self.assertFalse(ui.toggle)
            self.assertFalse(ui.session_state['direct_chat'])
            self.assertTrue(any('Research setup' in w.value for w in ui.warning))
            ui.sidebar.button(key='history_'+direct).click().run()
            self.assertTrue(ui.session_state['direct_chat'])
            self.assertEqual(ui.session_state['active_conversation_id'],direct)
            self.assertFalse(ui.exception)

    def test_long_history_is_trimmed_before_model_call(self):
        model=Model()
        history=[{'role':'user' if n%2==0 else 'assistant','content':'long context '*1000} for n in range(12)]
        with patch.object(bridge,'_make_client',return_value=model):
            result=bridge.run_direct_chat('Hello',history,bridge.configuration(direct=True))
        self.assertTrue(result.successful)
        self.assertLess(len(model.calls[0][0]),14)


if __name__=='__main__': unittest.main()
