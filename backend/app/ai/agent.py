"""LangGraph AI Agent orchestration and provider routing.

Uses langgraph.prebuilt.create_react_agent — a pre-built ReAct agent that:
  1. Sends the conversation to the LLM.
  2. If the LLM calls a tool, executes it and loops back.
  3. When the LLM produces a final text response, the loop ends.

Provider abstraction:
  The LLM is constructed by get_llm() based on AI_PROVIDER / AI_MODEL env vars.

System prompt:
  Tells the agent it is a ticket management assistant, what tools it has, and to
  always reply in the same language the user wrote in (Spanish or English).
"""

import logging
from functools import lru_cache
from langchain_core.messages import SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.ai.tools import make_tools
from app.ai import observability
from app.ai.checkpoint import get_checkpointer
from app.ai.state import AgentState
from app.services.ai_metrics_service import AIRunTracker

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an AI assistant for D4-Ticket AI, a professional ticketing system.
You help users manage their tickets through natural language.

You have access to the following tools:
- query_tickets: search and filter tickets (returns status, priority, title, and ID)
- get_ticket: get details of a specific ticket
- get_ticket_history: get the audit history of a specific ticket
- create_ticket: create a new ticket
- change_status: change a ticket's status
- add_comment: add a comment to a ticket
- update_ticket: update title, description or client info
- find_users: search users by name (partial match). Use this before reassigning when the user gives a name, not an email.
- reassign_ticket: reassign a ticket to another user by their email
- delete_ticket: request deletion of a ticket. Call this tool immediately when the user asks to delete a ticket. If the user is the author, the system will show a confirmation dialog. If not, the system may offer to notify the author instead.
- search_knowledge: search the internal knowledge base for documentation, guides, or context

Guidelines:
- PRINCIPLE OF HUMAN-IN-THE-LOOP:
  - DIRECT COMMANDS: If the user explicitly asks you to perform an action (e.g., "Create a ticket for X", "Change ticket 123 to closed"), execute the tool immediately.
  - SUGGESTIONS/DIAGNOSIS: If YOU identify a problem or suggest a solution (e.g., "I think this ticket should be reassigned to Network experts"), YOU MUST NOT call the tool automatically. Instead, explain your reasoning and ASK THE USER for confirmation (e.g., "Do you want me to reassign it for you?").
  - Never modify the database state based on your own induction without explicit human consent.
- CONTEXT RESOLUTION & EXECUTION (WHICH TICKET TO MODIFY):
  - If the user issues a direct command (e.g., "change to high priority", "close this"), you MUST execute the appropriate tool IMMEDIATELY without asking for confirmation, using this priority:
    1. EXPLICIT: If the user explicitly names a specific ticket title or ID in their message, ALWAYS act on that.
    2. SELECTED/VIEWED: If no ticket is named, use the "CURRENTLY VIEWING" or "USER HAS SELECTED THESE TICKETS" from the system context. Execute the tool for EACH selected ticket IMMEDIATELY. The user's current selection ALWAYS overrides the conversation history.
    3. AMBIGUOUS: Only ask for clarification if there is no named ticket AND no selected/viewed ticket.
- TEMPORAL AWARENESS & GREETINGS:
  - ONLY if the user's message is EXCLUSIVELY a greeting (e.g., "hello", "hi", "good morning") AND there is a long period of inactivity, greet them back and mention any pending task.
  - IF THE USER GIVES A DIRECT COMMAND (e.g., "delete the ticket", "set it to high priority"), EXECUTE IT IMMEDIATELY regardless of the time passed since the last interaction. Commands ALWAYS override greetings.
- Always respond in the same language the user is writing in (Spanish or English).
- When you perform an action (create, update, comment), confirm it clearly.
- If you need a ticket ID and the user gave a partial ID or title, use query_tickets first.
- If the user asks who changed a ticket, when it changed, or what happened over time, use get_ticket_history.
- To find "urgent" tickets, use query_tickets (the most urgent will be at the top). The information in the list is sufficient; DO NOT call get_ticket for every result unless the user asks for full details.
- If multiple tickets have the same maximum priority, the oldest ones are considered more urgent. Explain this reasoning to the user (e.g., "This ticket is critical and has been open the longest").
- Be concise and friendly. Avoid unnecessary technical jargon.
- Never invent ticket IDs or user emails — always verify with tools first.
- When reassigning a ticket and the user provides a name (not an email), always call find_users first.
  Apply the CONTEXT RESOLUTION rule (above) to determine the target ticket BEFORE asking any question:
  use the selected/viewed ticket from context if no ticket is explicitly named — do NOT ask the user for the ticket.
  If exactly 1 user match is returned AND the ticket is already resolved from context, ask a single confirmation
  that includes both: "Should I assign ticket '[title]' to [Full Name]?" — then call reassign_ticket on confirmation.
  If the ticket is NOT in context and was not named, only then ask which ticket they mean.
  If multiple user matches, list them and ask the user to specify which full name they mean.
  Only ask for the email if there is still ambiguity after showing the matching names, or if find_users returns no matches.
  Never ask for the email if find_users already returned it — use it directly after user confirms.
- If an action fails, explain why clearly.
- If a question seems to be about a process, policy, or documentation topic, search_knowledge before answering from your own knowledge.
"""


def _resolve_primary_choice(preferred_provider: str | None) -> tuple[str, str]:
    """Resolve which provider and model to use for the primary LLM call.

    Explicit overrides (`"openai"`, `"google"`) win; `"auto"` (or `None`)
    falls back to `settings.AI_PROVIDER` / `settings.AI_MODEL`.

    Returns:
        tuple[str, str]: `(provider, model)` ready to be passed to the
        corresponding LangChain client.
    """
    normalized = (preferred_provider or "auto").lower()
    if normalized == "openai":
        return "openai", "gpt-4o-mini"
    if normalized == "google":
        return "google", "gemini-2.5-flash"
    default_model = settings.AI_MODEL or (
        "gemini-2.5-flash" if settings.AI_PROVIDER == "google" else "gpt-4o-mini"
    )
    return settings.AI_PROVIDER, default_model


@lru_cache(maxsize=4)
def get_llm(preferred_provider: str | None = None) -> BaseChatModel:
    """Return a cached chat-model client for the given provider.

    The cache is keyed on `preferred_provider`, so the four legal values
    (`None`, `"auto"`, `"openai"`, `"google"`) result in at most four
    long-lived clients reused across requests.
    """
    return _build_llm(preferred_provider)


def _build_llm(preferred_provider: str | None = None) -> BaseChatModel:
    """Build the primary chat model and wrap it with a cross-provider fallback.

    The primary is the one chosen by `_resolve_primary_choice`; when keys
    for the other provider are available, it is wired up as a
    `.with_fallbacks([...])` so transient outages of the primary fall
    through to the secondary transparently. Configuration-level errors
    (e.g. missing keys) are **not** caught — those should fail loudly at
    startup.

    Raises:
        ValueError: If the API key for the chosen primary provider is
            not configured.
    """
    primary_provider, primary_model = _resolve_primary_choice(preferred_provider)

    if primary_provider == "google":
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY no encontrada. Revisa tu archivo .env en la carpeta backend.")
        from langchain_google_genai import ChatGoogleGenerativeAI
        primary_llm = ChatGoogleGenerativeAI(
            model=primary_model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0,
            streaming=True,
            max_retries=0,  # fail fast to trigger fallback
        )
    else:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY no encontrada para el proveedor primario.")
        from langchain_openai import ChatOpenAI
        primary_llm = ChatOpenAI(
            model=primary_model,
            api_key=settings.OPENAI_API_KEY,
            temperature=0,
            streaming=True,
        )

    # 2. Fallback LLM — only for transient errors (network, quota), not config errors
    fallback_llm = None
    fallback_model = None

    if primary_provider == "google" and settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            fallback_llm = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=settings.OPENAI_API_KEY,
                temperature=0,
                streaming=True,
                request_timeout=30.0,
            )
            fallback_model = "gpt-4o-mini"
        except ImportError:
            logger.warning("AI Agent: langchain-openai not installed — fallback disabled.")
    elif primary_provider == "openai" and settings.GOOGLE_API_KEY:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            fallback_llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0,
                streaming=True,
                max_retries=0,
            )
            fallback_model = "gemini-2.5-flash"
        except ImportError:
            logger.warning("AI Agent: langchain-google-genai not installed — fallback disabled.")

    if fallback_llm is not None:
        logger.info("AI Agent: %s (with %s fallback)", primary_model, fallback_model)
        observability.configure(
            provider=primary_provider,
            model=primary_model,
            fallback_available=True,
            fallback_model=fallback_model,
        )
        return primary_llm.with_fallbacks(
            [fallback_llm],
            exceptions_to_handle=(Exception,),
        )
    else:
        logger.warning("AI Agent: Fallback disabled (missing key or library).")

    observability.configure(
        provider=primary_provider,
        model=primary_model,
        fallback_available=False,
    )
    logger.info("AI Agent: %s (no fallback)", primary_model)
    return primary_llm


def build_agent(
    db: AsyncSession,
    actor: User,
    system_context: str = "",
    metrics_tracker: AIRunTracker | None = None,
    preferred_provider: str | None = None,
):
    """Compile a ReAct agent bound to the current request.

    The returned graph carries the LLM, the per-request tool bindings
    (which embed `db` and `actor` into their closures), the persistent
    PostgreSQL checkpointer and an optional `system_context` block
    appended to the static `SYSTEM_PROMPT`.

    Args:
        db: Async SQLAlchemy session forwarded to the tools.
        actor: Authenticated user the agent acts on behalf of.
        system_context: Extra runtime context (e.g. "user is viewing
            ticket 42") appended verbatim to the system prompt.
        metrics_tracker: Optional `AIRunTracker` shared with the tools so
            tool calls and RAG hits are counted in the AIRun row.
        preferred_provider: Optional provider override.

    Returns:
        CompiledGraph: LangGraph agent ready to be invoked or streamed.
    """
    llm = get_llm(preferred_provider)
    tools = make_tools(db, actor, metrics_tracker=metrics_tracker)

    checkpointer = get_checkpointer()

    full_prompt = SYSTEM_PROMPT
    if system_context:
        full_prompt += f"\n\n{system_context}"

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=full_prompt),
        checkpointer=checkpointer,
        state_schema=AgentState,
    )
