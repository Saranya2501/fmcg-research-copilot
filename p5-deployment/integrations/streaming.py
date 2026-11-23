"""Adapt live provider chunks to P2's existing completion, cache and usage flow."""
import re
from types import SimpleNamespace


def visible_text(raw):
    text = re.sub(r'<think>.*?</think>\s*', '', raw, flags=re.DOTALL)
    text = text.split('<think>', 1)[0]
    # A tag can arrive across several chunks; don't flash a partial opening tag.
    for length in range(1, len('<think>')):
        if text.endswith('<think>'[:length]):
            text = text[:-length]
            break
    return text.strip()


def enable_streaming(client, on_text):
    """Keep P2 retries/locking/cache; only adapt the provider's wire response."""
    completions = client._client.chat.completions
    create = completions.create

    def streamed_create(**params):
        raw, finish, usage = '', None, None
        on_text('')  # Reset any partial output before a retry.
        stream = create(**params, stream=True, stream_options={'include_usage': True})
        try:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    raw += choice.delta.content
                    on_text(visible_text(raw))
                if choice.finish_reason is not None:
                    finish = choice.finish_reason
            if finish is None:
                raise RuntimeError('Model stream ended before a completion marker')
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=raw, tool_calls=[]),
                                         finish_reason=finish)], usage=usage)
        finally:
            stream.close()

    completions.create = streamed_create
