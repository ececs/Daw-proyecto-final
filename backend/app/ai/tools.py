"""LangGraph Tool Factory Module with Pydantic Validation.

This module defines the suite of tools available to the AI agent. It uses
Pydantic schemas for argument validation, ensuring that the LLM provides
correctly formatted data (UUIDs, Enums, etc.) before hitting the database.

Available Tools:
- query_tickets: search and filter tickets with pagination.
- get_ticket: fetch complete details of a single ticket.
- create_ticket: create a new support ticket.
- change_status: transition a ticket between workflow states.
- add_comment: append a message to a ticket thread.
- update_ticket: update any field in a ticket (priority, title, etc.).
- search_knowledge: query the semantic knowledge base (RAG).
- delete_ticket: permanently remove a ticket (requires interrupt).
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
    """Lowercase + strip diacritics for accent-insensitive comparison."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


# --- Pydantic Schemas for Tool Arguments ---

class QueryTicketsSchema(BaseModel):
    """Validation schema for querying and filtering system tickets."""
    status: Optional[str] = Field(None, description="Filter by: open, in_progress, in_review, closed")
    priority: Optional[str] = Field(None, description="Filter by: low, medium, high, critical")
    search: Optional[str] = Field(None, description="Text to search in the ticket title")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")

class GetTicketSchema(BaseModel):
    """Validation schema for retrieving discrete ticket details."""
    ticket_id: str = Field(..., description="The UUID string of the ticket")

class GetTicketHistorySchema(BaseModel):
    """Validation schema for fetching ticket historical audit trails."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    limit: int = Field(15, ge=1, le=50, description="Max history entries to return")

class CreateTicketSchema(BaseModel):
    """Validation schema for creating new ticketing incidents."""
    title: str = Field(..., description="Concise title of the issue")
    description: Optional[str] = Field(None, description="Detailed context")
    priority: str = Field("medium", description="low, medium, high, or critical")
    assignee_email: Optional[str] = Field(None, description="Email of the user to assign")
    client_url: Optional[str] = Field(None, description="Client's website URL for analysis")
    client_summary: Optional[str] = Field(None, description="Brief summary of who the client is and what they do")

class ReassignTicketSchema(BaseModel):
    """Validation schema for performing user reassignment events."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    assignee_email: str = Field(
        ...,
        description="Email of the user to assign, or 'unassign' to clear. If find_users returned exactly one confirmed match, use that email from the tool result instead of asking the user for it again."
    )

class ChangeStatusSchema(BaseModel):
    """Validation schema for performing state workflow transitions."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    new_status: str = Field(..., description="New state: open, in_progress, in_review, closed")

class AddCommentSchema(BaseModel):
    """Validation schema for appending textual messages to ticket threads."""
    ticket_id: str = Field(..., description="UUID of the target ticket")
    content: str = Field(..., description="Text content of the comment")

class UpdateTicketSchema(BaseModel):
    """Validation schema for modifying multiple general ticket parameters."""
    ticket_id: str = Field(..., description="UUID of the ticket")
    title: Optional[str] = Field(None, description="New title")
    description: Optional[str] = Field(None, description="New description")
    priority: Optional[str] = Field(None, description="New priority: low, medium, high, critical")
    assignee_email: Optional[str] = Field(None, description="New assignee email, or 'unassign'")
    client_url: Optional[str] = Field(None, description="New client website URL")
    client_summary: Optional[str] = Field(None, description="New client profile summary")

class SearchKnowledgeSchema(BaseModel):
    """Validation schema for executing semantic vector-space RAG queries."""
    query: str = Field(..., description="The question or search phrase")
    k: int = Field(5, ge=1, le=10, description="Number of passages to retrieve")

class AIDiagnoseSchema(BaseModel):
    """Validation schema for initiating automated AI Co-pilot diagnoses."""
    ticket_id: str = Field(..., description="UUID of the ticket to diagnose")

class FindUsersSchema(BaseModel):
    """Validation schema for searching user records by textual name matching."""
    name: str = Field(
        ...,
        description="Partial or full name to search for (case-insensitive). Use this before reassigning when the user gives a name instead of an email."
    )

class DeleteTicketSchema(BaseModel):
    """Validation schema for triggering high-risk ticket deletion signals."""
    ticket_id: str = Field(..., description="UUID of the ticket to delete")

# --- Tool Factory ---

def make_tools(db: AsyncSession, actor: User, metrics_tracker: AIRunTracker | None = None) -> List:
    """Constructs a collection of validated, scoped tools for the agent graph.

    Embeds active transaction boundaries and security context (authenticated actor)
    directly into the tool execution lifecycle. Employs locks to maintain
    operational atomicity inside the shared graph session.

    Args:
        db: Active asynchronous SQLAlchemy transactional session.
        actor: The authenticated User model executing the agent graph session.
        metrics_tracker: Runtime telemetry tracker configured for the execution run.

    Returns:
        List: Collection of LangChain tools bound with defined argument schemas.
    """
    lock = asyncio.Lock()

    @tool(args_schema=QueryTicketsSchema)
    async def query_tickets(status=None, priority=None, search=None, limit=10) -> str:
        """Executes a query to search and filter existing ticketing incidents.

        Leverages hybrid search capabilities when searching by text, or falls back
        to priority-sorted deterministic ordering.

        Returns:
            str: Formatted list string containing status, priority, and ticket keys.
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
                    # Hybrid search (same engine as the UI table)
                    tickets = await ticket_service.hybrid_search_tickets(db, base, search, pool=limit * 5)
                    tickets = tickets[:limit]
                else:
                    # No search — sort by priority (Critical first) then oldest first (FIFO)
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
        """Retrieves detailed descriptive information for a single discrete ticket.

        Returns:
            str: Formatted summary outlining the title, status, and full description.
        """
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
        """Recovers the chronological audit trail for a specified ticket incident.

        Returns:
            str: A multi-line string documenting mutation events, actors, and datetimes.
        """
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
        """Creates a new ticketing incident record populated with client metadata context.

        Returns:
            str: Operation success message displaying the generated ticket UUID.
        """
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
        """Performs an atomic workflow state transition on an active ticket.

        Returns:
            str: Success string confirming completion of the transition.
        """
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
        """Appends a new threaded textual commentary entry onto an active ticket.

        Returns:
            str: Success indicator confirming comment persistence.
        """
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
        """Modifies multiple arbitrary attribute fields associated with a ticket.

        Triggers background indexing workflows automatically if client URL properties undergo updates.

        Returns:
            str: Update status confirmation message.
        """
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
                
                # If URL changed, trigger background scraping
                if client_url:
                    import asyncio
                    asyncio.create_task(scraping_service.scrape_and_index_url(tid, client_url))

                return "Ticket successfully updated."
            except Exception as e:
                return f"Error: {e}"

    @tool(args_schema=SearchKnowledgeSchema)
    async def search_knowledge(query: str, k: int = 5) -> str:
        """Queries the vectorized knowledge repository executing RAG lookups.

        Returns:
            str: A concatenated string of text passages yielding semantic proximity to query.
        """
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
        """Invokes the AI Co-pilot engine to execute a multi-hop incident diagnosis.

        Returns:
            str: Comprehensive diagnostic textual reasoning containing remediation proposals.
        """
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
                return f"Error al generar diagnóstico: {e}"

    @tool(args_schema=ReassignTicketSchema)
    async def reassign_ticket(ticket_id: str, assignee_email: str) -> str:
        """Executes user ownership reassignment binding tickets to target emails.

        Returns:
            str: Final assignment confirmation summary indicating success.
        """
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
        """Searches matching user system accounts employing case-insensitive partial names.

        Returns:
            str: Enumeration of matching profiles displaying name and primary contact email.
        """
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
                        f"'¿Asigno a {u.name}?'. "
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
        """Issues a deletion request signal triggering human-in-the-loop approval gateways.

        Returns:
            str: Specially serialized confirmation signal to be intercepted by the SSE router.
        """
        async with lock:
            try:
                tid = uuid.UUID(ticket_id)
                result = await db.execute(select(Ticket).where(Ticket.id == tid))
                ticket = result.scalar_one_or_none()
                if not ticket:
                    return "Ticket not found."
                if ticket.author_id != actor.id:
                    return f"__DELETE_REQUEST_OFFER__:{ticket_id}:{ticket.title}"
                title = ticket.title
            except ValueError:
                return f"Invalid ticket ID: {ticket_id}"
            except Exception as e:
                return f"Error: {e}"

        # Return the marker with the real title — the router intercepts this
        # and sends a 'confirmation_required' SSE event to the frontend.
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
