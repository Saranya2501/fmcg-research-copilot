"""Render chat messages, usage, sources, and elapsed time."""

import re

import streamlit as st

_working_timer = st.components.v2.component(
    "fmcg_working_timer",
    html='<small role="timer">Working for 0s</small>',
    js="""
    const timers = new WeakMap();

    export default function renderTimer({ parentElement }) {
        const label = parentElement.querySelector('[role="timer"]');
        const previous = timers.get(parentElement);
        if (previous) clearInterval(previous.interval);
        const started = previous?.started ?? performance.now();

        function update() {
            const seconds = Math.floor((performance.now() - started) / 1000);
            const minutes = Math.floor(seconds / 60);
            const elapsed = minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
            label.textContent = `Working for ${elapsed}`;
        }

        update();
        const interval = setInterval(update, 1000);
        timers.set(parentElement, { started, interval });
        return () => {
            clearInterval(interval);
            timers.delete(parentElement);
        };
    }
    """,
)


def render_working_timer() -> None:
    _working_timer(key="working_timer")


def display_answer(message):
    content = message["content"]
    for citation in message.get("citations") or []:
        chunk_id = citation.get("source_id") or citation.get("chunk_id")
        if chunk_id:
            marker = re.escape(f"[{chunk_id}]")
            content = re.sub(r"[ \t]*" + marker + r"(?!\(|\[)", "", content)
    return content


def format_elapsed_time(latency_ms: float) -> str:
    if latency_ms < 1000:
        return "less than 1s"
    minutes, seconds = divmod(round(latency_ms / 1000), 60)
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def render_messages(messages):
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(display_answer(message) if message["role"] == "assistant" else message["content"])
            if message["role"] == "assistant":
                usage = message.get("response", {}).get("usage") or {}
                if all(usage.get(key) is not None for key in
                       ("prompt_tokens", "completion_tokens", "total_tokens")):
                    st.caption(
                        f"Tokens · Input: {usage['prompt_tokens']:,} · "
                        f"Output: {usage['completion_tokens']:,} · "
                        f"Total: {usage['total_tokens']:,}"
                    )
                else:
                    st.caption("Tokens · Usage unavailable")
                citations = message.get("citations") or []
                rag = message.get("response", {}).get("metrics", {}).get("rag") or {}
                passages = rag.get("passages") or []
                if citations or passages:
                    with st.expander("Sources"):
                        for citation in citations:
                            st.write(f"{citation.get('company','')} · {citation.get('document',citation.get('doc',''))} · p. {citation.get('page','?')}")
                        if passages:
                            st.caption(f"Retrieved passages: {len(passages)}")
                if message.get("response",{}).get("limitations"):
                    st.caption("Limitations: " + "; ".join(message["response"]["limitations"]))
                latency_ms = message.get("latency_ms")
                if latency_ms is not None:
                    st.caption(f"Worked for {format_elapsed_time(latency_ms)}")

