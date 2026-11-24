"""Streamlit chat view and interaction flow."""

from contextlib import nullcontext
import logging
import time

import streamlit as st

from storage.history_repository import create_conversation, load_messages, find_resume_conversation, conversation_mode
from chat.chat_settings import positive_setting, retrieval_enabled, response_config
from chat.rate_limit import check_rate_limit
from chat.chat_service import process_chat_turn
from ui.session import require_user_session
from ui.sidebar import render_sidebar
from ui.messages import render_messages, render_working_timer
from ui.styles import apply_chat_styles
from storage.redis_connection import get_redis_client

logger = logging.getLogger(__name__)

STARTER_QUESTIONS = (
    "What was ITC's FMCG segment revenue in FY24?",
    "What did HUL report about urban versus rural demand in FY24?",
)


def main() -> None:
    st.set_page_config(page_title="FMCG Research Copilot", page_icon="📊")
    try:
        get_redis_client()
    except Exception:
        logger.exception("Redis connection or Search capability check failed")
        st.error("Redis is unavailable or missing Search support. Check REDIS_URL and the Redis service.")
        st.stop()
    apply_chat_styles()
    from ui.browser_session import restore_browser_session, save_browser_session
    restore_browser_session()
    user_session_id, user_name = require_user_session()
    if "active_conversation_id" not in st.session_state:
        selected = find_resume_conversation(user_session_id, st.query_params.get("chat"))
        st.session_state.active_conversation_id = (
            selected or create_conversation(user_session_id=user_session_id))
    st.query_params['chat'] = st.session_state.active_conversation_id
    save_browser_session(user_session_id, st.session_state.active_conversation_id)
    if "request_timestamps" not in st.session_state:
        st.session_state.request_timestamps = []
    if 'direct_chat' not in st.session_state:
        st.session_state.direct_chat = conversation_mode(st.session_state.active_conversation_id) == 'chat'
    try:
        if not retrieval_enabled():
            st.session_state.direct_chat = True
        limit = positive_setting("CHAT_RATE_LIMIT", 5)
        window = positive_setting("CHAT_RATE_WINDOW_SECONDS", 60)
        positive_setting("CHAT_CACHE_TTL_SECONDS", 3600)
        if st.session_state.direct_chat:
            from integrations.agent_bridge import configuration
            configuration(direct=True)
        else:
            response_config()
    except (ValueError, OSError, ImportError) as exc:
        logger.exception("Invalid chat configuration.")
        st.error(f"Invalid chat configuration: {exc}")
        st.stop()

    render_sidebar(user_session_id, user_name)

    st.session_state.messages = load_messages(st.session_state.active_conversation_id)

    st.title("FMCG Research Copilot")
    if st.session_state.direct_chat:
        from integrations.api_connection import connection
        if connection().missing():
            st.warning('Set up your API key, base URL and model ID to start chatting.')
    elif response_config()["backend"] == "agent":
        from integrations.agent_bridge import missing_setup
        missing = missing_setup()
        if missing:
            st.warning("Research setup is incomplete. Source data or model configuration is still needed.")
            with st.expander("Setup details"):
                for item in missing:
                    st.write(item)

    suggestions = None
    suggested_question = None
    if not st.session_state.messages:
        suggestions = st.empty()
        with suggestions.container(key="starter_questions"):
            for starter in STARTER_QUESTIONS:
                if st.button(starter, width="stretch", wrap=True):
                    suggested_question = starter

    render_messages(st.session_state.messages)

    placeholder = (
        "Message your model…" if st.session_state.direct_chat
        else "Ask about a company, financial year, or competitor…"
    )
    question = st.chat_input(placeholder, max_chars=5000) or suggested_question
    if question and question.strip():
        timestamps, retry_after = check_rate_limit(
            st.session_state.request_timestamps, time.monotonic(), limit, window
        )
        st.session_state.request_timestamps = timestamps
        if retry_after:
            st.warning(f"Message limit reached. Try again in {retry_after} seconds.")
            return
        if suggestions is not None:
            suggestions.empty()
        question = question.strip()
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            output = st.empty()
            render_working_timer()
            def show_stream(text):
                output.markdown(text + " ▌" if text else "Thinking…")
            with st.spinner("Thinking…") if st.session_state.direct_chat else nullcontext():
                process_chat_turn(question, st.session_state.active_conversation_id,
                    mode='chat' if st.session_state.direct_chat else 'research',
                    on_text=show_stream if st.session_state.direct_chat else None,
                    on_progress=None if st.session_state.direct_chat else output.caption,
                    user_session_id=user_session_id)
        st.rerun()
