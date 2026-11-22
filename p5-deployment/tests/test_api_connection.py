import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI as RealOpenAI, AuthenticationError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import api_connection
import agent_bridge
from p4_loader import load_p2


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        root=Path(self.folder.name)
        self.settings=patch.dict(os.environ,{
            'LLM_BASE_URL':'https://api.groq.com/openai/v1','LLM_API_KEY':'fake-test-key',
            'LLM_MODEL':'test-model','LLM_JSON_MODE':'true','LLM_TLS_CA_CERT':'',
            'LLM_TARGET':'local','LLM_CA_CERT':'/does-not-exist/institute.crt',
            'LLM_CACHE':'1','LLM_LOG_PATH':str(root/'calls.jsonl'),
            'LLM_CACHE_PATH':str(root/'cache.sqlite'),'LLM_LOCK_PATH':str(root/'api.lock'),
        })
        self.settings.start()
        self.requests=[]
        self.reject=False
        def handler(request):
            self.requests.append(request)
            if self.reject:
                return httpx.Response(401,json={'error':{'message':'Invalid fake-test-key'}})
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'test-model',
                'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':5,'completion_tokens':3,'total_tokens':8}})
        def factory(**kwargs):
            kwargs['http_client'].close()
            kwargs['http_client']=httpx.Client(transport=httpx.MockTransport(handler))
            return RealOpenAI(**kwargs)
        self.factory=factory

    def tearDown(self):
        self.settings.stop();self.folder.cleanup()

    def make(self):
        modules=load_p2(agent_bridge.p2_path())
        with patch.object(agent_bridge,'get_tracing_client',return_value=None),patch('openai.OpenAI',side_effect=self.factory):
            return agent_bridge._make_client(modules['llm_client'])

    def test_three_settings_activate_compatible_mode_without_certificate(self):
        settings=api_connection.connection()
        self.assertEqual(settings.mode,'compatible')
        self.assertEqual(settings.missing(),[])
        self.assertNotIn('fake-test-key',repr(settings))
        self.assertEqual(agent_bridge.configuration()['provider'],'compatible')

    def test_wire_request_has_correct_key_endpoint_model_and_no_qwen_flags(self):
        client=self.make()
        try:
            result=client.chat([{'role':'user','content':'Return JSON.'}],response_format={'type':'json_object'})
            self.assertEqual(result.usage['total_tokens'],8)
            request=self.requests[0]
            self.assertEqual(str(request.url),'https://api.groq.com/openai/v1/chat/completions')
            self.assertEqual(request.headers['authorization'],'Bearer fake-test-key')
            body=json.loads(request.content)
            self.assertEqual(body['model'],'test-model')
            self.assertNotIn('chat_template_kwargs',body)
            self.assertEqual(body['messages'][0]['content'],'Return JSON.')
            self.assertEqual(body['response_format'],{'type':'json_object'})
        finally: agent_bridge._close_client(client)

    def test_model_cache_and_evaluation_bypass_are_preserved(self):
        client=self.make()
        try:
            messages=[{'role':'user','content':'Return JSON.'}]
            first=client.chat(messages)
            second=client.chat(messages)
            self.assertFalse(first.cached);self.assertTrue(second.cached)
            client.chat(messages,use_cache=False)
            self.assertEqual(len(self.requests),2)
        finally: agent_bridge._close_client(client)

    def test_json_mode_can_be_disabled_for_other_compatible_servers(self):
        with patch.dict(os.environ,{'LLM_JSON_MODE':'false'}): client=self.make()
        try:
            client.chat([{'role':'user','content':'Return JSON.'}],response_format={'type':'json_object'})
            self.assertNotIn('response_format',json.loads(self.requests[0].content))
        finally: agent_bridge._close_client(client)

    def test_missing_settings_and_bad_urls_are_actionable(self):
        with patch.dict(os.environ,{'LLM_API_KEY':'','LLM_MODEL':''}):
            self.assertEqual(api_connection.connection().missing(),['LLM_API_KEY','LLM_MODEL'])
        for value in ('not-a-url','https://user:password@example.test/v1','https://example.test/v1/chat/completions'):
            with self.subTest(value=value),patch.dict(os.environ,{'LLM_BASE_URL':value}):
                with self.assertRaises(ValueError): api_connection.connection()

    def test_local_and_institute_modes_remain_available(self):
        with patch.dict(os.environ,{'LLM_BASE_URL':'','LLM_TARGET':'local'}):
            self.assertEqual(api_connection.connection().mode,'local')
        with patch.dict(os.environ,{'LLM_BASE_URL':'','LLM_TARGET':'api','LLM_API_BASE_URL':'https://institute.invalid/v1'}):
            settings=api_connection.connection()
            self.assertEqual(settings.mode,'api')
            self.assertIn('valid LLM_CA_CERT file',settings.missing())
        with patch.dict(os.environ,{'LLM_BASE_URL':'','LLM_TARGET':'api','LLM_MODEL':''}):
            self.assertEqual(api_connection.connection().model,'Qwen/Qwen3-8B')

    def test_cache_namespace_changes_for_endpoint_model_and_json_mode(self):
        original=agent_bridge.configuration()
        self.assertNotIn('fake-test-key',json.dumps(original))
        for key,value,field in (('LLM_BASE_URL','https://other-provider.invalid/v1','endpoint_fingerprint'),
                                ('LLM_MODEL','other-model','model'),('LLM_JSON_MODE','false','json_mode')):
            with patch.dict(os.environ,{key:value}):
                self.assertNotEqual(original[field],agent_bridge.configuration()[field])

    def test_authentication_failure_does_not_log_the_key_or_cache_response(self):
        self.reject=True
        client=self.make()
        try:
            with self.assertRaises(AuthenticationError):
                client.chat([{'role':'user','content':'Return JSON.'}])
            log=Path(os.environ['LLM_LOG_PATH']).read_text()
            self.assertNotIn('fake-test-key',log)
            self.assertEqual(client._db.execute('SELECT count(*) FROM cache').fetchone()[0],0)
        finally: agent_bridge._close_client(client)


if __name__=='__main__': unittest.main()
