import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app
import tracing


class TracingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exporter = InMemorySpanExporter()
        cls.client = Langfuse(
            public_key="pk-lf-local-test", secret_key="sk-lf-local-test",
            base_url="http://localhost:1", tracer_provider=TracerProvider(),
            span_exporter=cls.exporter, mask_otel_spans=tracing.mask_export,
        )

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"CHAT_HISTORY_DB": self.folder.name + "/history.sqlite3"})
        self.env.start()
        self.exporter.clear()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def test_hierarchy_session_masking_and_saved_history(self):
        conversation = app.create_conversation()
        with patch.object(tracing, "get_tracing_client", return_value=self.client):
            app.process_chat_turn("Contact test@example.com with sk-lf-secret-test", conversation)
        self.client.flush()
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        root = next(s for s in spans if s.name == "process-chat-turn")
        child = next(s for s in spans if s.name == "respond-preview")
        self.assertEqual(child.parent.span_id, root.context.span_id)
        self.assertIsNone(root.parent)
        for span in spans:
            attrs = dict(span.attributes)
            self.assertIn(conversation, str(attrs))
            self.assertNotIn("test@example.com", str(attrs))
            self.assertNotIn("sk-lf-secret-test", str(attrs))
            self.assertNotIn("gen_ai.usage.input_tokens", attrs)
        self.assertEqual(len(app.load_messages(conversation)), 2)

    def test_missing_credentials_and_disabled_tracing(self):
        for settings in ({"LANGFUSE_TRACING_ENABLED": "false"}, {"LANGFUSE_PUBLIC_KEY": ""}):
            with patch.dict(os.environ, settings):
                tracing.get_tracing_client.cache_clear()
                self.assertIsNone(tracing.get_tracing_client())
        tracing.get_tracing_client.cache_clear()

    def test_trace_setup_failure_does_not_duplicate_messages(self):
        from unittest.mock import Mock
        broken_client = Mock()
        broken_client.start_as_current_observation.side_effect = RuntimeError("offline")
        conversation = app.create_conversation()
        with patch.object(tracing, "get_tracing_client", return_value=broken_client):
            reply = app.process_chat_turn("HUL revenue", conversation)
        self.assertIn("preview", reply)
        self.assertEqual(len(app.load_messages(conversation)), 2)

    def test_application_error_is_recorded_without_raw_exception(self):
        with patch.object(tracing, "get_tracing_client", return_value=self.client):
            with self.assertRaises(RuntimeError):
                with tracing.trace_step("failing-operation", question="test", conversation_id="test-session"):
                    raise RuntimeError("secret-error-value")
        self.client.flush()
        span = self.exporter.get_finished_spans()[0]
        self.assertIn("ERROR", str(dict(span.attributes)))
        self.assertNotIn("secret-error-value", str(span.events))


if __name__ == "__main__":
    unittest.main()
