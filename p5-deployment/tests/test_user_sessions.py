import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from chat import chat_service
from integrations import tracing
from storage.response_cache import ChatResponse
from streamlit.testing.v1 import AppTest


class UserSessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'CHAT_HISTORY_DB': self.folder.name + '/history.sqlite3',
            'CHAT_BACKEND': 'preview', 'CHAT_CACHE_ENABLED': 'true'})
        self.env.start()
        self.trace = patch.object(tracing, 'get_tracing_client', return_value=None)
        self.trace.start()

    def tearDown(self):
        self.trace.stop()
        self.env.stop()
        self.folder.cleanup()

    def test_name_required_and_session_survives_reruns(self):
        ui = AppTest.from_file(str(Path(app.__file__))).run()
        self.assertEqual(len(ui.chat_input), 0)
        ui.text_input[0].set_value('   ')
        ui.button[0].click().run()
        self.assertTrue(ui.error)
        with app.history_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_sessions').fetchone()[0], 0)
        ui.text_input[0].set_value(' Sam ')
        ui.button[0].click().run()
        self.assertFalse(ui.exception)
        session = ui.session_state['user_session_id']
        ui.run()
        self.assertEqual(ui.session_state['user_session_id'], session)
        self.assertEqual(len(ui.text_input), 0)
        self.assertEqual(len(ui.chat_input), 1)
        with app.history_db() as db:
            self.assertEqual(db.execute('SELECT name FROM user_sessions WHERE id=?', (session,)).fetchone()[0], 'Sam')

    def test_refresh_restores_session_chat_and_total_only_summary(self):
        ui = AppTest.from_file(str(Path(app.__file__))).run()
        ui.text_input[0].set_value('Sam')
        ui.button[0].click().run()
        session = ui.session_state['user_session_id']
        chat = ui.session_state['active_conversation_id']
        app.save_message(chat, 'user', 'Remember this')
        app.save_message(chat, 'assistant', 'Saved answer', response={
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
        refreshed = AppTest.from_file(str(Path(app.__file__)))
        refreshed.query_params.update(dict(ui.query_params))
        refreshed.run()
        self.assertFalse(refreshed.exception)
        self.assertEqual(len(refreshed.text_input), 0)
        self.assertEqual(refreshed.session_state['user_session_id'], session)
        self.assertEqual(refreshed.session_state['active_conversation_id'], chat)
        self.assertEqual(refreshed.session_state['messages'][-1]['content'], 'Saved answer')
        summary = [c.value for c in refreshed.sidebar.caption if c.value.startswith('Session tokens')]
        self.assertEqual(summary, ['Session tokens · Total: 15'])
        with app.history_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_sessions').fetchone()[0], 1)

    def test_new_chat_saves_resume_id_on_click(self):
        session = app.create_user_session('Sam')
        previous = app.create_conversation(user_session_id=session)
        ui = AppTest.from_file(str(Path(app.__file__)))
        ui.query_params.update({'session': session, 'chat': previous})
        ui.run()
        with patch('ui.browser_session.save_browser_session') as save_resume:
            next(button for button in ui.sidebar.button if button.label == 'New chat').click().run()
        self.assertFalse(ui.exception)
        current = ui.session_state['active_conversation_id']
        self.assertNotEqual(current, previous)
        save_resume.assert_called_once_with(session, current)

    def test_refresh_does_not_open_another_sessions_chat(self):
        session = app.create_user_session('Sam')
        own = app.create_conversation(user_session_id=session)
        other = app.create_conversation(user_session_id=app.create_user_session('Other'))
        ui = AppTest.from_file(str(Path(app.__file__)))
        ui.query_params.update({'session': session, 'chat': other})
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state['active_conversation_id'], own)

    def test_separate_sessions_even_with_same_name_and_usage_across_chats(self):
        first, second = app.create_user_session('Sam'), app.create_user_session('Sam')
        self.assertNotEqual(first, second)
        chats = [app.create_conversation(user_session_id=first) for _ in range(2)]
        other = app.create_conversation(user_session_id=second)
        result = ChatResponse('Answer', usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15})
        with patch.object(chat_service, 'generate_response', return_value=result):
            for chat in chats:
                app.process_chat_turn('Question', chat, user_session_id=first)
            app.process_chat_turn('Question', other, user_session_id=second)
        self.assertEqual(app.session_usage(first)['total_tokens'], 30)
        self.assertEqual(app.session_usage(second)['total_tokens'], 15)
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            app.process_chat_turn('Question', other, user_session_id=first)

    def test_history_filtered_and_old_chats_not_claimed(self):
        old = app.create_conversation()
        app.save_message(old, 'user', 'Legacy chat')
        ui = AppTest.from_file(str(Path(app.__file__))).run()
        ui.text_input[0].set_value('Sam')
        ui.button[0].click().run()
        session = ui.session_state['user_session_id']
        other = app.create_conversation(user_session_id=app.create_user_session('Other'))
        app.save_message(other, 'user', 'Private other chat')
        ui.chat_input[0].set_value('My chat').run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.sidebar.button), 2)  # New chat and this session's chat.
        self.assertFalse(any(b.label == 'Legacy chat' for b in ui.sidebar.button))
        self.assertFalse(any(b.label == 'Private other chat' for b in ui.sidebar.button))
        self.assertEqual(app.session_usage(session)['total_tokens'], 0)

    def test_cached_usage_does_not_inflate_totals(self):
        session = app.create_user_session('Sam')
        fresh, cached = [app.create_conversation(user_session_id=session) for _ in range(2)]
        config = {'backend': 'chat'}
        result = ChatResponse('Answer', cacheable=True,
            usage={'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15})
        with patch.object(chat_service, 'response_config', return_value=config), patch.object(chat_service, 'generate_response', return_value=result) as generate:
            app.process_chat_turn('Question', fresh, user_session_id=session)
            app.process_chat_turn('Question', cached, user_session_id=session)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(app.session_usage(session)['total_tokens'], 15)
        self.assertEqual(app.load_messages(cached)[-1]['response']['usage']['total_tokens'], 0)
