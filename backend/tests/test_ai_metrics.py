import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_feedback import AIFeedback
from app.models.ai_run import AIRun
from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.ticket_history import TicketHistory
from app.models.user import User


async def _create_ticket(
    db_session: AsyncSession,
    test_user: User,
    **overrides,
) -> dict:
    current_max = await db_session.scalar(select(func.max(Ticket.ticket_number)))
    ticket = Ticket(
        id=uuid.uuid4(),
        ticket_number=(current_max or 0) + 1,
        title=overrides.get("title", "AI metrics ticket"),
        description=overrides.get("description"),
        status=overrides.get("status", TicketStatus.open),
        priority=overrides.get("priority", TicketPriority.medium),
        author_id=test_user.id,
        assignee_id=overrides.get("assignee_id"),
        client_url=overrides.get("client_url"),
        client_summary=overrides.get("client_summary"),
    )
    db_session.add(ticket)
    await db_session.flush()
    db_session.add(
        TicketHistory(
            ticket_id=ticket.id,
            actor_id=test_user.id,
            field="created",
            old_value=None,
            new_value=None,
            created_at=ticket.created_at,
        )
    )
    await db_session.commit()
    return {
        "id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
    }


async def test_ai_status_endpoint_exposes_extended_operational_fields(client: AsyncClient):
    response = await client.get("/api/v1/ai/status")
    assert response.status_code == 200
    data = response.json()
    assert {
        "provider",
        "model",
        "fallback_available",
        "fallback_model",
        "action_count",
        "chat_count",
        "diagnoses_count",
        "rag_queries_count",
        "rag_hits_count",
        "fallback_count",
        "success_count",
        "error_count",
        "last_latency_ms",
        "avg_latency_ms",
        "last_surface",
        "last_rag_source",
    } <= set(data)


async def test_ai_feedback_endpoint_upserts_single_vote_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    ai_run = AIRun(
        id=uuid.uuid4(),
        user_id=test_user.id,
        surface="chat",
        provider="openai",
        model="gpt-4o-mini",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        success=True,
    )
    db_session.add(ai_run)
    await db_session.commit()

    first = await client.post(
        "/api/v1/ai/feedback",
        json={"ai_run_id": str(ai_run.id), "helped": True, "label": "helpful"},
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/api/v1/ai/feedback",
        json={"ai_run_id": str(ai_run.id), "helped": False, "label": "not_helpful"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["helped"] is False

    count = await db_session.scalar(select(func.count()).select_from(AIFeedback))
    assert count == 1


async def test_ai_stats_summary_distinguishes_closed_tickets_with_and_without_ai(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    ticket_with_ai = await _create_ticket(db_session, test_user, title="Closed with AI")
    ticket_without_ai = await _create_ticket(db_session, test_user, title="Closed without AI")

    run = AIRun(
        id=uuid.uuid4(),
        ticket_id=uuid.UUID(ticket_with_ai["id"]),
        user_id=test_user.id,
        thread_id="thread-with-ai",
        surface="diagnosis",
        provider="openai",
        model="gpt-4o-mini",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        latency_ms=1000,
        success=True,
        tool_actions_count=1,
        rag_queries_count=2,
        rag_hits_count=1,
        estimated_input_tokens=120,
        estimated_output_tokens=80,
        estimated_cost_usd=Decimal("0.001200"),
    )
    db_session.add(run)
    await db_session.commit()

    db_session.add(
        AIFeedback(
            ai_run_id=run.id,
            user_id=test_user.id,
            helped=True,
            label="helped_close",
        )
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/tickets/{ticket_with_ai['ticket_number']}",
        json={"status": "closed"},
    )
    assert response.status_code == 200
    response = await client.patch(
        f"/api/v1/tickets/{ticket_without_ai['ticket_number']}",
        json={"status": "closed"},
    )
    assert response.status_code == 200

    stats_response = await client.get("/api/v1/ai/stats")
    assert stats_response.status_code == 200, stats_response.text
    stats = stats_response.json()
    assert stats["total_runs"] == 1
    assert stats["tickets_closed_with_ai"] == 1
    assert stats["tickets_closed_without_ai"] == 1
    assert stats["positive_feedback_count"] == 1
    assert stats["total_rag_queries"] == 2
    assert stats["total_estimated_cost_usd"] == 0.0012


async def test_reply_draft_endpoint_generates_text_and_tracks_run(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    created = await _create_ticket(
        db_session,
        test_user,
        title="Reply draft ticket",
        description="Ticket for AI reply draft",
        client_summary="Cliente con problema de DNS ya resuelto.",
    )

    async def fake_reply(*args, **kwargs):
        tracker = kwargs.get("tracker")
        if tracker:
            tracker.provider = "openai"
            tracker.model = "gpt-4o-mini"
            tracker.input_tokens = 100
            tracker.append_output("Hemos aplicado la corrección y el servicio vuelve a estar operativo.")
        return "Hemos aplicado la corrección y el servicio vuelve a estar operativo."

    with patch("app.services.ai_copilot_service.get_ticket_reply_draft", side_effect=fake_reply):
        response = await client.post(
            f"/api/v1/tickets/{created['ticket_number']}/reply-draft",
            json={
                "resolution_note": "Se corrigió la configuración DNS y se limpió caché.",
                "preferred_provider": "openai",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "operativo" in data["draft"]
    assert data["ai_run_id"]

    ai_run = await db_session.get(AIRun, uuid.UUID(data["ai_run_id"]))
    assert ai_run is not None
    assert ai_run.surface == "reply_draft"
    assert ai_run.ticket_id == uuid.UUID(created["id"])
    assert ai_run.success is True
    assert ai_run.provider == "openai"
    assert ai_run.model == "gpt-4o-mini"


async def test_reply_draft_endpoint_returns_404_for_missing_ticket(client: AsyncClient):
    response = await client.post(
        f"/api/v1/tickets/{uuid.uuid4()}/reply-draft",
        json={"resolution_note": "Se reinició el servicio."},
    )
    assert response.status_code == 404


async def test_reply_draft_endpoint_rejects_blank_note(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    created = await _create_ticket(db_session, test_user, title="Blank note ticket")
    response = await client.post(
        f"/api/v1/tickets/{created['ticket_number']}/reply-draft",
        json={"resolution_note": "   "},
    )
    assert response.status_code == 422


async def test_ticket_ai_stats_uses_first_close_and_aggregates_feedback(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    created = await _create_ticket(db_session, test_user, title="Ticket stats detail")
    ticket_id = uuid.UUID(created["id"])
    ticket = await db_session.get(Ticket, ticket_id)
    assert ticket is not None

    base_time = datetime(2026, 5, 9, 9, 0, tzinfo=timezone.utc)
    ticket.created_at = base_time

    history_rows = (
        await db_session.execute(select(TicketHistory).where(TicketHistory.ticket_id == ticket_id))
    ).scalars().all()
    created_row = next(row for row in history_rows if row.field == "created")
    created_row.created_at = base_time

    db_session.add_all(
        [
            TicketHistory(
                ticket_id=ticket_id,
                actor_id=test_user.id,
                field="status",
                old_value="open",
                new_value="closed",
                created_at=base_time + timedelta(hours=2),
            ),
            TicketHistory(
                ticket_id=ticket_id,
                actor_id=test_user.id,
                field="status",
                old_value="closed",
                new_value="open",
                created_at=base_time + timedelta(hours=3),
            ),
            TicketHistory(
                ticket_id=ticket_id,
                actor_id=test_user.id,
                field="status",
                old_value="open",
                new_value="closed",
                created_at=base_time + timedelta(hours=5),
            ),
        ]
    )

    diagnosis_run = AIRun(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        user_id=test_user.id,
        surface="diagnosis",
        provider="openai",
        model="gpt-4o-mini",
        started_at=base_time + timedelta(minutes=30),
        completed_at=base_time + timedelta(minutes=31),
        latency_ms=60000,
        success=True,
        rag_queries_count=2,
        rag_hits_count=1,
        estimated_cost_usd=Decimal("0.000900"),
    )
    chat_run = AIRun(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        user_id=test_user.id,
        thread_id="ticket-thread",
        surface="chat",
        provider="openai",
        model="gpt-4o-mini",
        started_at=base_time + timedelta(hours=1),
        completed_at=base_time + timedelta(hours=1, minutes=1),
        latency_ms=60000,
        success=True,
        rag_queries_count=1,
        rag_hits_count=1,
        estimated_cost_usd=Decimal("0.001100"),
    )
    db_session.add_all([diagnosis_run, chat_run])
    await db_session.flush()
    db_session.add_all(
        [
            AIFeedback(ai_run_id=diagnosis_run.id, user_id=test_user.id, helped=True, label="helpful"),
            AIFeedback(ai_run_id=chat_run.id, user_id=test_user.id, helped=False, label="not_helpful"),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/ai/stats/tickets/{created['ticket_number']}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["diagnosis_runs"] == 1
    assert data["chat_runs"] == 1
    assert data["rag_queries_count"] == 3
    assert data["time_to_close_hours"] == 2.0
    assert data["estimated_cost_usd"] == 0.002


async def test_diagnosis_stream_emits_ai_run_id_and_persists_run(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    ticket = await _create_ticket(db_session, test_user, title="Streaming diagnosis")

    async def _fake_stream(*args, **kwargs):
        yield {"type": "token", "content": "Diagnostico de prueba"}

    with patch("app.api.v1.tickets.ai_copilot_service.stream_ticket_diagnosis", side_effect=_fake_stream):
        response = await client.get(f"/api/v1/tickets/{ticket['ticket_number']}/diagnosis")

    assert response.status_code == 200
    body = response.text.strip().split("\n\n")
    session_payload = json.loads(body[0].replace("data: ", ""))
    done_payload = json.loads(body[-1].replace("data: ", ""))
    assert session_payload["type"] == "session"
    assert session_payload["ai_run_id"]
    assert done_payload["type"] == "done"

    runs = (
        await db_session.execute(select(AIRun).where(AIRun.ticket_id == uuid.UUID(ticket["id"])))
    ).scalars().all()
    assert len(runs) == 1
    assert runs[0].surface == "diagnosis"
    assert runs[0].success is True
