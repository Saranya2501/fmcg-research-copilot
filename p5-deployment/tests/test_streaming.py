from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.streaming import enable_streaming, visible_text


class StreamingTests(unittest.TestCase):
    def chunk(self, text=None, finish=None, usage=None):
        return SimpleNamespace(usage=usage, choices=[] if usage else [
            SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish)])

    def test_delivers_text_before_provider_finishes_and_keeps_usage(self):
        updates = []
        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7)
        def chunks():
            yield self.chunk('Hello')
            self.assertEqual(updates[-1], 'Hello')
            yield self.chunk(' world')
            yield self.chunk(finish='stop')
            yield self.chunk(usage=usage)
        wire = Mock()
        wire.__iter__ = Mock(return_value=chunks())
        create = Mock(return_value=wire)
        client = SimpleNamespace(_client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create))))
        enable_streaming(client, updates.append)
        result = client._client.chat.completions.create(model='test', messages=[])
        self.assertEqual(updates, ['', 'Hello', 'Hello world'])
        self.assertEqual(result.choices[0].message.content, 'Hello world')
        self.assertIs(result.usage, usage)
        self.assertTrue(create.call_args.kwargs['stream'])
        self.assertEqual(create.call_args.kwargs['stream_options'], {'include_usage': True})
        wire.close.assert_called_once()

    def test_interrupted_stream_fails_and_closes_connection(self):
        wire = Mock()
        wire.__iter__ = Mock(return_value=iter([self.chunk('Partial')]))
        client = SimpleNamespace(_client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=Mock(return_value=wire)))))
        enable_streaming(client, lambda text: None)
        with self.assertRaisesRegex(RuntimeError, 'completion marker'):
            client._client.chat.completions.create(model='test', messages=[])
        wire.close.assert_called_once()

    def test_reasoning_and_partial_tags_are_hidden(self):
        for raw in ('<', '<thi', '<think>private', '<think>private</think>'):
            self.assertEqual(visible_text(raw), '')
        self.assertEqual(visible_text('<think>private</think>Answer'), 'Answer')


if __name__ == '__main__':
    unittest.main()
