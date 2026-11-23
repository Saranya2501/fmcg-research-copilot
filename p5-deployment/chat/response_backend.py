"""Backend adapter dispatch for research, direct chat, and preview."""

from chat.chat_models import ChatResponse

def generate_response(question: str, history: list[dict], filters: dict, config: dict, *, on_text=None, on_progress=None) -> ChatResponse:
    if config['backend']=='chat':
        from integrations.agent_bridge import run_direct_chat
        return run_direct_chat(question, history, config, on_text=on_text)
    if config["backend"] == "agent":
        from integrations.agent_bridge import run_agent
        return run_agent(question, history, filters, config, on_progress=on_progress)
    return ChatResponse(
        answer="I'm ready to help with your research. This is a preview of the chat; "
               "the research agent still needs to be connected before I can look up "
               "filings and provide an answer with citations.",
        cacheable=False,
    )
