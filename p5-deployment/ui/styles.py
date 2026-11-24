"""Existing chat presentation styles, isolated from application logic."""

import streamlit as st

def apply_chat_styles():
    st.markdown("""
        <style>
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"] {
            display: none;
        }
        [data-testid="stChatMessage"] {
            gap: 0;
        }
        [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
            width: fit-content;
            max-width: 80%;
            margin-left: auto;
            margin-right: 0;
            padding: 0.75rem 1rem;
            border-radius: 1rem 1rem 0.25rem 1rem;
        }
        [data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) {
            width: 100%;
            margin-left: 0;
            margin-right: auto;
            padding-left: 0;
            background: transparent;
        }
        [data-testid="stChatMessageContent"] {
            min-width: 0;
            text-align: left;
            overflow-wrap: anywhere;
        }
        .st-key-starter_questions button {
            justify-content: flex-start;
        }
        .st-key-starter_questions button,
        .st-key-starter_questions button p {
            text-align: left;
        }
        @media (max-width: 640px) {
            [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {
                max-width: 92%;
            }
        }
        [data-testid="stSidebar"] .st-key-chat_history [data-testid="stVerticalBlock"] {
            gap: 0;
        }
        [data-testid="stSidebar"] .st-key-chat_history button {
            width: 100%;
            background: transparent;
            border: 0;
            border-bottom: 1px solid rgba(128, 128, 128, 0.3);
            border-radius: 0;
            box-shadow: none;
            color: inherit;
            display: flex;
            justify-content: flex-start !important;
            text-align: left !important;
            padding: 0.65rem 0.5rem;
            min-height: 2.5rem;
        }
        [data-testid="stSidebar"] .st-key-chat_history button > div,
        [data-testid="stSidebar"] .st-key-chat_history button > div > div {
            width: 100% !important;
            min-width: 0;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [data-testid="stSidebar"] .st-key-chat_history button [data-testid="stMarkdownContainer"] {
            display: block !important;
            width: 100%;
            flex: 1 1 auto !important;
            text-align: left !important;
        }
        [data-testid="stSidebar"] .st-key-chat_history button p {
            width: 100%;
            text-align: left !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin: 0;
        }
        [data-testid="stSidebar"] .st-key-chat_history button:hover {
            background: rgba(128, 128, 128, 0.1);
            color: inherit;
        }
        [data-testid="stSidebar"] .st-key-chat_history button[kind="primary"] {
            background: rgba(128, 128, 128, 0.16);
            font-weight: 600;
        }
        [data-testid="stSidebar"] .st-key-chat_history button:focus-visible {
            outline: 2px solid var(--primary-color, #ff4b4b);
            outline-offset: -2px;
        }
        </style>
    """, unsafe_allow_html=True)
