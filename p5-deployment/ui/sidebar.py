"""Conversation history and mode controls."""

import streamlit as st

from storage.history_repository import session_usage, conversation_title, list_conversations
from ui.session import start_mode_conversation, select_conversation

def render_sidebar(user_session_id, user_name, allow_retrieval):
    with st.sidebar:
        st.subheader("📊 FMCG Copilot")
        st.text(f"Hello, {user_name}")
        usage = session_usage(user_session_id)
        st.caption(f"Session tokens · Total: {usage['total_tokens']:,}")
        st.button("New chat", width="stretch", on_click=start_mode_conversation)
        st.toggle('Chat with model',key='direct_chat',on_change=start_mode_conversation,
                  disabled=not allow_retrieval,
                  help='Skip document retrieval and talk directly to your configured model.')
        conversations = list_conversations(user_session_id)
        st.caption("CHAT HISTORY")
        if not conversations:
            st.caption("Your conversations will appear here.")
        with st.container(key="chat_history"):
            for conversation in conversations:
                title = conversation_title(conversation["first_message"]) if conversation["first_message"] else "New chat"
                st.button(
                    title,
                    key=f"history_{conversation['id']}",
                    type="primary" if conversation["id"] == st.session_state.active_conversation_id else "secondary",
                    width="stretch",
                    on_click=select_conversation,args=(conversation['id'],conversation['mode']),
                )

