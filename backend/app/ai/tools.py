"""LangGraph tools exposed to the AI agent.

Each tool is a Pydantic-validated callable that the LLM can invoke through
the ReAct loop. The factory `make_tools` binds the active SQLAlchemy
session, the authenticated user and an optional `AIRunTracker` into the
closure of every tool so the LLM never has to handle those plumbing
concerns.

A single `asyncio.Lock` is shared across all tools to serialise database
work on the same session — the LLM occasionally produces parallel tool
calls and the SQLAlchemy `AsyncSession` is not safe for concurrent use.

**Important:** the docstring of each `@tool` function becomes the natural-
language description the LLM reads when deciding which tool to call.
Rewording them changes the agent's behaviour; keep the wording faithful
to what the function actually does.
"""

import uuid
import logging
import asyncio
import unicodedata
from typing import Optional, List
from pydantic import BaseModel, Field

from langchain_core.tools import tool
from sqlalchemy import select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketStatus, TicketPriority
from app.models.user import User
from app.services.ai_metrics_service import AIRunTracker

from app.services import ticket_service, notification_service, knowledge_service, comment_service, scraping_service, history_service

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Lowercase and strip diacritics for accent-insensitive comparison."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


# --- Pydantic argument schemas (one per tool) ---

class QueryTicketsSchema(BaseModel):
    """Arguments for `query_tickets`."""
    status: Optional[str] = Field(None, description="Filter by: open, in_progress, in_review, closed")
    priority: Optional[str] = Field(None, description="Filter by: low, medium, high, critical")
    search: Optional[str] = Field(None, description="Text to search in the ticket title")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")


class GetTicketSchema(BaseModel):
    """Arguments for `get_ticket`."""
    ticket_id: str = Field(..., description="The UUID string of the ticket")


class GetTicketHistorySchema(BaseModel):
    """Arguments for `get_ticket_history`."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    limit: int = Field(15, ge=1, le=50, description="Max history entries to return")


class CreateTicketSchema(BaseModel):
    """Arguments for `create_ticket`."""
    title: str = Field(..., description="Concise title of the issue")
    description: Optional[str] = Field(None, description="Detailed context")
    priority: str = Field("medium", description="low, medium, high, or critical")
    assignee_email: Optional[str] = Field(None, description="Email of the user to assign")
    client_url: Optional[str] = Field(None, description="Client's website URL for analysis")
    client_summary: Optional[str] = Field(None, description="Brief summary of who the client is and what they do")


class ReassignTicketSchema(BaseModel):
    """Arguments for `reassign_ticket`."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    assignee_email: str = Field(
        ...,
        description="Email of the user to assign, or 'unassign' to clear. If find_users returned exactly one confirmed match, use that email from the tool result instead of asking the user for it again."
    )


class ChangeStatusSchema(BaseModel):
    """Arguments for `change_status`."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    new_status: str = Field(..., description="New state: open, in_progress, in_review, closed")


class AddCommentSchema(BaseModel):
    """Arguments for `add_comment`."""
    ticket_id: str = Field(..., description="UUID of the target ticket")
    content: str = Field(..., description="Text content of the comment")


class UpdateTicketSchema(BaseModel):
    """Arguments for `update_ticket`."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    title: Optional[str] = Field(None, description="New title")
    description: Optional[str] = Field(None, description="New description")
    priority: Optional[str] = Field(None, description="New priority: low, medium, high, critical")
    assignee_email: Optional[str] = Field(None, description="New assignee email, or 'unassign'")
    client_url: Optional[str] = Field(None, description="New client website URL")
    client_summary: Optional[str] = Field(None, description="New client profile summary")


class SearchKnowledgeSchema(BaseModel):
    """Arguments for `search_knowledge`."""
    query: str = Field(..., description="The question or search phrase")
    k: int = Field(5, ge=1, le=10, description="Number of passages to retrieve")


class AIDiagnoseSchema(BaseModel):
    """Arguments for `ai_diagnose_ticket`."""
    ticket_id: str = Field(..., description="UUID of the ticket to diagnose")


class FindUsersSchema(BaseModel):
    """Arguments for `find_users`."""
    name: str = Field(
        ...,
        description="Partial or full name to search for (case-insensitive). Use this before reassigning when the user gives a name instead of an email."
    )


class DeleteTicketSchema(BaseModel):
    """Arguments for `delete_ticket`."""
    ticket_id: str = Field(..., description="UUID of the ticket to delete")


def make_tools(db: AsyncSession, actor: User, metrics_tracker: AIRunTracker | None = None) -> List:
    """Build the list of tools bound to the current request.

    Captures `db`, `actor` and `metrics_tracker` in closures so every tool
    operates with the right session, identity and telemetry plumbing. A
    shared `asyncio.Lock` serialises database access to keep the
    `AsyncSession` single-threaded.

    Args:
        db: Async SQLAlchemy session for the agent run.
        actor: Authenticated user the agent is acting on behalf of.
        metrics_tracker: Optional tracker shared with the surrounding
            AIRun so tool calls and RAG hits get counted.

    Returns:
        list: LangChain `BaseTool` instances ready to be plugged into
        `create_react_agent`.
    """
    lock = asyncio.Lock()

    @tool(args_schema=QueryTicketsSchema)
    async def query_tickets(status=None, priority=None, search=None, limit=10) -> str:
        """Search and filter tickets. Returns status, priority, title and ID.

        Uses the hybrid keyword + vector search when `search` is given;
        otherwise sorts by priority (critical first) then oldest first.
        """
        logger.info(f"AI Tool: query_tickets(status={status}, priority={priority}, search={search})")
        async with lock:
            try:
                base = select(Ticket)
                if status:
                    try:
                        base = base.where(Ticket.status == TicketStatus(status))
                    except ValueError:
                        return f"Invalid status '{status}'."
                if priority:
                    try:
                        base = base.where(Ticket.priority == TicketPriority(priority))
                    except ValueError:
                        return f"Invalid priority '{priority}'."

                if search:
                    tickets = await ticket_service.hybrid_search_tickets(db, base, search, pool=limit * 5)
                    tickets = tickets[:limit]
                else:
                    # Why: critical first, then FIFO so the oldest critical
                    # ticket surfaces at the top of the list.
                    priority_order = case(
                        (Ticket.priority == TicketPriority.critical, 1),
                        (Ticket.priority == TicketPriority.high, 2),
                        (Ticket.priority == TicketPriority.medium, 3),
                        (Ticket.priority == TicketPriority.low, 4),
                        else_=5,
                    )
                    result = await db.execute(
                        base.order_by(priority_order, Ticket.created_at.asc()).limit(limit)
                    )
                    tickets = result.scalars().all()

                if not tickets:
                    return "No tickets found with the specified filters."

                return "\n".join([
                    f"  [#{t.ticket_number}] [{t.status.value}] [{t.priority.value}] {t.title} (ID: {t.id})"
                    for t in tickets
                ])
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=GetTicketSchema)
    async def get_ticket(ticket_id: str) -> str:
        """Get details of a specific ticket (title, status, description)."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                ticket = await ticket_service.get_ticket(db, tid)
                if not ticket:
                    return "Ticket not found."
                return f"Title: {ticket.title}\nStatus: {ticket.status.value}\nDescription: {ticket.description}"
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=GetTicketHistorySchema)
    async def get_ticket_history(ticket_id: str, limit: int = 15) -> str:
        """Get the audit history of a ticket (who changed what, when)."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                entries = await history_service.get_history(db, tid, limit=limit)
                if not entries:
                    return "No history found for this ticket."
                lines = []
                for e in entries:
                    actor = e.actor.name if e.actor else "Unknown"
                    when = e.created_at.strftime("%Y-%m-%d %H:%M")
                    if e.field == "created":
                        lines.append(f"[{when}] {actor} created the ticket")
                    elif e.old_value and e.new_value:
                        lines.append(f"[{when}] {actor} changed {e.field} from '{e.old_value}' to '{e.new_value}'")
                    elif e.new_value:
                        lines.append(f"[{when}] {actor} set {e.field} to '{e.new_value}'")
                    else:
                        lines.append(f"[{when}] {actor} updated {e.field}")
                return "\n".join(lines)
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=CreateTicketSchema)
    async def create_ticket(title, description=None, priority="medium", assignee_email=None, client_url=None, client_summary=None) -> str:
        """Create a new ticket. Returns the new ticket id."""
        async with lock:
            try:
                prio = TicketPriority(priority)
                assignee_id = None
                if assignee_email:
                    res = await db.execute(select(User).where(User.email == assignee_email))
                    user = res.scalar_one_or_none()
                    if not user: return f"User {assignee_email} not found."
                    assignee_id = user.id

                ticket = await ticket_service.create_ticket(
                    db,
                    title=title,
                    description=description,
                    priority=prio,
                    author_id=actor.id,
                    assignee_id=assignee_id,
                    client_url=client_url,
                    client_summary=client_summary
                )
                return f"Ticket created. ID: {ticket.id}"
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=ChangeStatusSchema)
    async def change_status(ticket_id: str, new_status: str) -> str:
        """Change the status of a ticket (open, in_progress, in_review, closed)."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                status = TicketStatus(new_status)
                ticket = await ticket_service.update_ticket(db, tid, {"status": status}, actor)
                if not ticket: return "Ticket not found."
                return f"Status updated to {new_status}."
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=AddCommentSchema)
    async def add_comment(ticket_id: str, content: str) -> str:
        """Add a comment to a ticket."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                comment = await comment_service.create_comment(db, ticket_id=tid, content=content, author=actor)
                if not comment:
                    return f"Ticket {ticket_id} not found."

                return "Comment successfully added."
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=UpdateTicketSchema)
    async def update_ticket(
        ticket_id: str,
        title=None,
        description=None,
        priority=None,
        assignee_email=None,
        client_url=None,
        client_summary=None
    ) -> str:
        """Update one or more fields of a ticket. Triggers re-scraping if client_url changes."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                update_data = {}
                if title: update_data["title"] = title
                if description: update_data["description"] = description
                if priority: update_data["priority"] = TicketPriority(priority)
                if client_url: update_data["client_url"] = client_url
                if client_summary: update_data["client_summary"] = client_summary

                if assignee_email:
                    if assignee_email.lower() == "unassign":
                        update_data["assignee_id"] = None
                    else:
                        res = await db.execute(select(User).where(User.email == assignee_email))
                        user = res.scalar_one_or_none()
                        if not user: return f"User {assignee_email} not found."
                        update_data["assignee_id"] = user.id

                updated_ticket = await ticket_service.update_ticket(db, tid, update_data, actor)

                if client_url:
                    import asyncio
                    asyncio.create_task(scraping_service.scrape_and_index_url(tid, client_url))

                return "Ticket successfully updated."
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=SearchKnowledgeSchema)
    async def search_knowledge(query: str, k: int = 5) -> str:
        """Search the internal knowledge base (RAG) for documentation or context."""
        async with lock:
            try:
                result = await knowledge_service.search_with_stats(db, query, k=k)
                chunks = [chunk.content for chunk in result.chunks]
                if metrics_tracker:
                    metrics_tracker.record_rag(1, 1 if result.hits else 0, result.source_type)
                else:
                    from app.ai import observability
                    observability.increment_rag_query(had_results=bool(chunks))
                return "\n\n".join(chunks) if chunks else "No information found."
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=AIDiagnoseSchema)
    async def ai_diagnose_ticket(ticket_id: str) -> str:
        """Run the AI co-pilot diagnosis on a ticket and return the suggested fix."""
        async with lock:
            try:
                from app.services import ai_copilot_service
                tid = uuid.UUID(ticket_id)
                diagnosis = await ai_copilot_service.get_ticket_diagnosis(
                    db,
                    tid,
                    tracker=metrics_tracker,
                    preferred_provider=metrics_tracker.primary_provider if metrics_tracker else None,
                )
                return diagnosis
            except Exception as e:
                return f"Error generating diagnosis: {e}"

    @tool(args_schema=ReassignTicketSchema)
    async def reassign_ticket(ticket_id: str, assignee_email: str) -> str:
        """Reassign a ticket to another user identified by email (or 'unassign')."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                assignee_id = None
                if assignee_email.lower() != "unassign":
                    res = await db.execute(select(User).where(User.email == assignee_email))
                    user = res.scalar_one_or_none()
                    if not user: return f"User {assignee_email} not found."
                    assignee_id = user.id

                await ticket_service.update_ticket(db, tid, {"assignee_id": assignee_id}, actor)
                return f"Ticket successfully reassigned to {assignee_email}."
            except Exception as e:
                return f"Error reassigning ticket: {e}"

    @tool(args_schema=FindUsersSchema)
    async def find_users(name: str) -> str:
        """Search users by partial name (case- and accent-insensitive). Returns name + email."""
        async with lock:
            try:
                needle = _normalize(name)
                result = await db.execute(select(User).order_by(User.name))
                users = [u for u in result.scalars().all() if needle in _normalize(u.name)]
                if not users:
                    return f"No users found matching '{name}'. Ask the user for their exact email."
                if len(users) == 1:
                    u = users[0]
                    return (
                        f"Found exactly 1 match: {u.name} ({u.email}). "
                        f"Ask the user to confirm using the full name only, for example: "
                        f"'Should I assign it to {u.name}?'. "
                        f"If the user confirms, call reassign_ticket with this email: {u.email}."
                    )
                lines = "\n".join(f"  - {u.name} ({u.email})" for u in users)
                return (
                    f"Found {len(users)} users matching '{name}':\n{lines}\n"
                    "Ask the user which full name they mean. Only ask for the email if the names are still ambiguous."
                )
            except Exception as e:
                return f"Error searching users: {e}"

    @tool(args_schema=DeleteTicketSchema)
    async def delete_ticket(ticket_id: str) -> str:
        """Request deletion of a ticket. The frontend intercepts the marker string and shows a confirmation."""
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                result = await db.execute(select(Ticket).where(Ticket.id == tid))
                ticket = result.scalar_one_or_none()
                if not ticket:
                    return "Ticket not found."
                # Why: when the actor is not the author we return a different
                # marker so the SSE router offers to *notify* the author
                # instead of deleting directly.
                if ticket.author_id != actor.id:
                    return f"__DELETE_REQUEST_OFFER__:{ticket_id}:{ticket.title}"
                title = ticket.title
            except ValueError:
                return f"Invalid ticket ID: {ticket_id}"
            except Exception as e:
                return f"Error: {e}"

        # Why: the marker is intercepted by the SSE router which emits a
        # `confirmation_required` event so the user can approve the delete.
        return f"__DELETE_REQUESTED__:{ticket_id}:{title}"

    return [
        query_tickets,
        get_ticket,
        get_ticket_history,
        create_ticket,
        change_status,
        add_comment,
        update_ticket,
        find_users,
        reassign_ticket,
        search_knowledge,
        ai_diagnose_ticket,
        delete_ticket,
    ]
