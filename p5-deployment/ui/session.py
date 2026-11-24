"""Streamlit user-session and conversation selection controller."""

import streamlit as st

from chat.chat_settings import retrieval_enabled
from storage.history_repository import create_user_session, create_conversation, require_conversation_owner, find_user_session

def require_user_session():
    identifier = st.session_state.get("user_session_id") or st.query_params.get("session")
    if identifier:
        user = find_user_session(identifier)
        if user:
            st.session_state.user_session_id = identifier
            st.query_params["session"] = identifier
            return identifier, user["name"]
    st.title("Welcome to FMCG Research Copilot")
    with st.form("start_session"):
        name = st.text_input("Your name", max_chars=80)
        submitted = st.form_submit_button("Continue")
    if submitted:
        try:
            identifier = create_user_session(name)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.user_session_id = identifier
            st.query_params["session"] = identifier
            st.query_params.pop("chat", None)
            for key in ("active_conversation_id", "messages", "direct_chat", "request_timestamps"):
                st.session_state.pop(key, None)
            st.rerun()
    st.stop()


def start_new_conversation():
    direct_chat = not retrieval_enabled()
    st.session_state.active_conversation_id = create_conversation(
        'chat' if direct_chat else 'research', user_session_id=st.session_state.user_session_id
    )
    st.session_state.direct_chat = direct_chat
    st.query_params["chat"] = st.session_state.active_conversation_id


def select_conversation(conversation_id,mode):
    require_conversation_owner(conversation_id, st.session_state.user_session_id)
    st.session_state.active_conversation_id=conversation_id
    st.session_state.direct_chat=mode=='chat'
    st.query_params['chat'] = conversation_id
