"""Render saved chat messages, usage, and sources."""

import re

import streamlit as st

def display_answer(message):
    content = message["content"]
    for citation in message.get("citations") or []:
        chunk_id = citation.get("source_id") or citation.get("chunk_id")
        if chunk_id:
            marker = re.escape(f"[{chunk_id}]")
            content = re.sub(r"[ \t]*" + marker + r"(?!\(|\[)", "", content)
    return content


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

