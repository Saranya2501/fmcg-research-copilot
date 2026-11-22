import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import response_cache as cache
import tracing


class ResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / "history.sqlite3")
        self.settings = patch.dict(os.environ, {
            "CHAT_HISTORY_DB": self.path, "CHAT_CACHE_ENABLED": "true",
            "CHAT_CACHE_TTL_SECONDS": "3600",
        })
        self.settings.start()
        self.offline = patch.object(tracing, "get_tracing_client", return_value=None)
        self.offline.start()
        self.config = {"backend": "test", "model": "test-model", "prompt_version": "v1", "corpus_version": "v1"}
        self.result = cache.ChatResponse("Revenue: 100 crore", [{"doc_id": "hul-fy24", "page": 1}], cacheable=True)

    def tearDown(self):
        self.offline.stop()
        self.settings.stop()
        self.folder.cleanup()

    def test_key_invalidation_and_canonical_order(self):
        make = cache.cache_key
        base = make("HUL FY24?", [], {"company": "HUL", "year": "FY24"}, self.config)
        self.assertEqual(base, make(" HUL FY24? ", [], {"year": "FY24", "company": "HUL"}, self.config))
        self.assertNotEqual(base, make("HUL FY23?", [], {"company": "HUL", "year": "FY24"}, self.config))
        for field in ("backend", "model", "provider", "generation", "prompt_version", "corpus_version", "pipeline_version"):
            self.assertNotEqual(base, make("HUL FY24?", [], {"company": "HUL", "year": "FY24"}, {**self.config, field: "changed"}))
        self.assertNotEqual(base, make("HUL FY24?", [], {"company": "ITC", "year": "FY24"}, self.config))
        history = [{"role": "user", "content": "HUL FY24?"}]
        self.assertNotEqual(make("and last year?", history, {}, self.config), make("and last year?", [], {}, self.config))

    def test_persistence_expiry_clear_and_corrupt_entry(self):
        with app.history_db() as db:
            cache.store(db, "key", self.result, 60, now=100)
        with app.history_db() as db:
            self.assertEqual(cache.lookup(db, "key", now=159), self.result)
            self.assertIsNone(cache.lookup(db, "key", now=160))
            cache.store(db, "key", self.result, 60, now=200)
            db.execute("UPDATE response_cache SET response_json = 'broken'")
            self.assertIsNone(cache.lookup(db, "key", now=201))
            cache.store(db, "key", self.result, 60, now=200)
            cache.clear(db)
            self.assertIsNone(cache.lookup(db, "key", now=201))

    def test_failed_empty_and_noncacheable_results_not_stored(self):
        with app.history_db() as db:
            for result in (cache.ChatResponse("preview"), cache.ChatResponse("error", successful=False, cacheable=True),
                           cache.ChatResponse(" ", cacheable=True)):
                cache.store(db, "key", result, 60)
                self.assertIsNone(cache.lookup(db, "key"))

    def test_hit_skips_generator_preserves_citations_and_history(self):
        with patch.object(app, "response_config", return_value=self.config), patch.object(app, "generate_response", return_value=self.result) as generate:
            first, second = app.create_conversation(), app.create_conversation()
            app.process_chat_turn("HUL FY24?", first)
            app.process_chat_turn("HUL FY24?", second)
            self.assertEqual(generate.call_count, 1)
            messages = app.load_messages(second)
            self.assertEqual(messages[-1]["cache_status"], "hit")
            self.assertEqual(messages[-1]["citations"], self.result.citations)
            self.assertEqual(len(messages), 2)
            app.process_chat_turn("HUL FY24?", second)  # Context changed.
            self.assertEqual(generate.call_count, 2)

    def test_bypass_disabled_preview_and_errors(self):
        for option in ("bypass", "disabled", "preview", "error"):
            with self.subTest(option=option):
                config = {**self.config, "backend": "preview"} if option == "preview" else self.config
                result = cache.ChatResponse("failed", successful=False, cacheable=True) if option == "error" else self.result
                with patch.object(app, "response_config", return_value=config), patch.object(app, "generate_response", return_value=result) as generate:
                    with patch.dict(os.environ, {"CHAT_CACHE_ENABLED": "false" if option == "disabled" else "true"}):
                        for _ in range(2):
                            app.process_chat_turn(option, app.create_conversation(), bypass_cache=option == "bypass")
                    self.assertEqual(generate.call_count, 2)

    def test_generator_exception_not_cached_and_cache_errors_fail_open(self):
        with patch.object(app, "response_config", return_value=self.config):
            with patch.object(app, "generate_response", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    app.process_chat_turn("question", app.create_conversation())
            with app.history_db() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM response_cache").fetchone()[0], 0)
            with patch.object(cache, "lookup", side_effect=sqlite3.OperationalError("unavailable")), patch.object(app, "generate_response", return_value=self.result) as generate:
                app.process_chat_turn("question", app.create_conversation())
                self.assertEqual(generate.call_count, 1)

    def test_legacy_history_migration_and_saved_links(self):
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT)")
                db.execute("INSERT INTO messages (conversation_id,role,content,created_at) VALUES ('old','assistant','Old answer','2026-01-01')")
        old = app.load_messages("old")[0]
        self.assertEqual(old["content"], "Old answer")
        self.assertIsNone(old["trace_url"])
        self.assertEqual(old["citations"], [])
        conversation = app.create_conversation()
        with patch.object(app, "trace_identity", return_value=("trace-1", "https://example.test/trace-1")):
            app.process_chat_turn("hello", conversation)
        saved = app.load_messages(conversation)[-1]
        self.assertEqual(saved["trace_id"], "trace-1")
        self.assertEqual(saved["trace_url"], "https://example.test/trace-1")
        self.assertGreaterEqual(saved["latency_ms"], 0)

    def test_trace_button_survives_reopening_chat(self):
        from streamlit.testing.v1 import AppTest
        with patch.object(tracing, "trace_identity", return_value=("trace-test", "https://example.test/traces/trace-test")):
            ui = AppTest.from_file(str(Path(app.__file__))).run()
            ui.chat_input[0].set_value("HUL revenue?").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.get("link_button")[0].proto.url, "https://example.test/traces/trace-test")
        conversation = ui.session_state["active_conversation_id"]
        ui.sidebar.button[0].click().run()
        ui.sidebar.button(key="history_" + conversation).click().run()
        self.assertEqual(len(ui.get("link_button")), 1)
        self.assertEqual(len(ui.session_state["messages"]), 2)

    def test_generation_settings_cannot_include_credentials(self):
        with patch.dict(os.environ, {"CHAT_GENERATION_CONFIG": '{"api_key":"do-not-export"}'}):
            with self.assertRaises(ValueError):
                app.response_config()


if __name__ == "__main__":
    unittest.main()
