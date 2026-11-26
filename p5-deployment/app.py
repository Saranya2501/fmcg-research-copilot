"""Streamlit entry point and compatibility imports for P5 callers."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

# Preserve the public functions used by existing scripts. New callers should
# import the responsible module directly.
from storage.database import history_db
from storage.history_repository import (
    create_conversation, create_user_session, session_usage,
    conversation_title, save_message, load_messages,
)
from chat.chat_settings import positive_setting, response_config
from chat.rate_limit import check_rate_limit
from chat.response_backend import generate_response
from chat.chat_service import process_chat_turn
from ui.chat import main

if __name__ == "__main__":
    main()
