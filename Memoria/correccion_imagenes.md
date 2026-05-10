# Corrección de Imágenes de la Memoria

Documento de revisión de las imágenes IA incluidas en `Memoria_revisada_trabajo.docx`.

Contexto que deben respetar todas las regeneraciones:

- El nombre del producto se mantiene como `D4-Ticket AI`.
- El proyecto DAW evoluciona por separado del reto original de Orbidi, así que la iconografía y los textos deben reflejar el estado real del repo actual.
- Frontend: `Next.js 16`, `React 19`, `TypeScript`, `Zustand`, `WebSockets`, `SSE`.
- Backend: `FastAPI`, `SQLAlchemy 2`, `Alembic`.
- Base de datos: `PostgreSQL 16 + pgvector`.
- Tiempo real: `WebSockets + Redis Pub/Sub` con fallback a `PostgreSQL NOTIFY`.
- Storage: `Cloudflare R2` en producción y `MinIO` en local.
- IA actual:
  - proveedor configurable por entorno
  - preferencia de usuario: `auto`, `GPT-4o-mini`, `Gemini 2.5 Flash`
  - fallback automático al proveedor alternativo
  - embeddings con `gemini-embedding-2`
- Agente: `LangGraph` con memoria persistente en PostgreSQL (`AsyncPostgresSaver` / checkpointer).
- Observabilidad y métricas:
  - `/ai/status`
  - `/ai/stats`
  - `/ai/stats/tickets/{ticket_ref}`
  - `/ai/feedback`
  - feedback `Ayudó / No ayudó`

## image1.png

Estado:
- Se puede mantener.

Observaciones:
- Funciona como portada decorativa y no introduce errores técnicos relevantes.

Prompt opcional si se quisiera regenerar:

```text
Create a premium editorial cover background for a technical project report titled "D4-Ticket AI". Soft blue and white palette, subtle luminous network lines, polished professional style, minimal futuristic ambience, clean central area reserved for the title, no fake UI text, vertical A4 composition.
```

## image2.png

Estado:
- Corregir.

Errores detectados:
- `CLIENT - Browser` y `BACKEND - Server Card` suenan genéricos y poco profesionales.
- No refleja el nuevo control de preferencia de proveedor.
- Falta separar claramente `SSE` para chat y `WebSockets` para tiempo real general.

Prompt detallado:

```text
Edit this architecture diagram while preserving the same polished pastel infographic style. Keep the product name "D4-Ticket AI". Use accurate labels and structure:
- Frontend (Next.js 16 + React 19 + Zustand)
- AI Control Panel (provider preference: Auto / GPT-4o-mini / Gemini 2.5 Flash)
- WebSockets (real-time sync and notifications)
- SSE (AI chat streaming)
- Backend (FastAPI Routers + Domain Services)
- PostgreSQL + pgvector
- Redis Pub/Sub
- Cloudflare R2
- LangGraph Agent
- OpenAI GPT-4o-mini
- Gemini 2.5 Flash
- gemini-embedding-2 embeddings
Do not imply that WebSockets are used for the chat stream. Clean Spanish labels, premium software architecture style, technically faithful.
```

## image3.png

Estado:
- Corregir.

Errores detectados:
- Muestra `OpenAI API` como fallback del agente, pero el sistema actual permite preferencia por usuario y fallback cruzado.
- `Google AI Studio (embeddings + Gemini)` es demasiado genérico para la explicación final.

Prompt detallado:

```text
Edit this deployment/integration diagram in the same visual style. Keep the title "D4-Ticket AI". Show the real platform roles:
- Vercel (frontend)
- Railway (backend FastAPI + PostgreSQL)
- Cloudflare R2 (adjunto storage)
- OpenAI API (GPT-4o-mini, selectable by user or used as fallback)
- Google AI Studio (Gemini 2.5 Flash selectable + gemini-embedding-2 embeddings)
Add a small note or label indicating that the active provider can be chosen from the UI and that automatic fallback exists between providers.
Use accurate Spanish labels, premium infographic look, no fake architecture roles.
```

## image4.png

Estado:
- Corregir.

Errores detectados:
- `Client Browser` y `Zustand State` están demasiado simplificados.
- `LangGraph Engine` no es el nombre usado actualmente.
- La flecha entre `WebSockets` y `LangGraph` puede sugerir mal el flujo del chat.
- `Google Gemini 2.5` debería ser `Gemini 2.5 Flash`.

Prompt detallado:

```text
Edit this technical architecture diagram while preserving the same clean pastel style. Keep the product name "D4-Ticket AI". Update labels to:
- Frontend Next.js 16
- Zustand global state
- AI Control Panel
- FastAPI Routers
- Domain Services
- LangGraph Agent
- PostgreSQL + pgvector
- Redis Pub/Sub
- Cloudflare R2
- OpenAI GPT-4o-mini
- Gemini 2.5 Flash
- SSE for AI chat streaming
- WebSockets for notifications and ticket synchronization
Avoid implying that LangGraph sends chat responses through WebSockets. Clean Spanish labels, precise software architecture diagram.
```

## image5.png

Estado:
- Rehacer.

Errores detectados:
- Duplica `tickets`.
- `users.role` no existe.
- `comments.body` no coincide con el modelo real (`content`).
- `attachments.file_url` no coincide con `storage_key`.
- `notifications.read_status` no coincide con `read`.
- `knowledge_chunks` no representa la estructura real.
- Falta `ticket_number`.

Prompt detallado:

```text
Generate a clean and accurate entity-relationship diagram for the D4-Ticket AI project database. Premium pastel technical infographic style, readable typography, no duplicated entities, no invented fields.

Real entities and fields:
- users: id, email, name, avatar_url, created_at
- tickets: id, ticket_number, title, description, status, priority, author_id, assignee_id, client_url, client_summary, embedding, created_at, updated_at
- comments: id, ticket_id, author_id, content, created_at
- attachments: id, ticket_id, uploader_id, filename, storage_key, size_bytes, mime_type, created_at, use_for_rag
- notifications: id, user_id, ticket_id, type, message, read, created_at
- ticket_history: id, ticket_id, actor_id, field, old_value, new_value, created_at
- knowledge_chunks: id, url, chunk_index, content, embedding, chunk_metadata, created_at

Show clear PK/FK relationships. Use exact English field names as listed. Do not add role, password_hash, file_url, read_status, duplicated tickets, duplicated users, or fake analytics tables.
```

## image6.png

Estado:
- Rehacer o eliminar en favor de una sola versión correcta del esquema.

Errores detectados:
- Duplica `USERS` y `COMMENTS`.
- Introduce `password_hash`, que no forma parte del modelo.
- Usa `priority int`, cuando el proyecto usa enums.
- Incluye `relevance_score` y otros campos inventados.

Prompt detallado:

```text
Create a polished database schema diagram for D4-Ticket AI that matches the real implementation exactly. Use a neat modern infographic style with a soft blue background and rounded cards, but keep all technical content faithful.

Do not duplicate entities.
Do not include password_hash.
Do not include file_url.
Do not include fake relevance_score or analytics fields.
Do include ticket_number in tickets.
Do include use_for_rag in attachments.
Do include chunk_metadata in knowledge_chunks.

Entities to show:
users, tickets, comments, attachments, notifications, ticket_history, knowledge_chunks

Use exact field names from the real schema and clear PK/FK labels.
```

## image7.png

Estado:
- Corregir.

Errores detectados:
- Aparece `migrations/`, pero en el proyecto real la carpeta es `alembic/`.

Prompt detallado:

```text
Edit this backend file-tree infographic while preserving layout and style. Replace the folder label "migrations/" with "alembic/". Update the subtitle to "Migraciones y revisiones Alembic". Keep the rest unchanged unless a tiny rebalancing is needed for visual clarity.
```

## image8.png

Estado:
- Rehacer.

Errores detectados:
- Usa stores inexistentes: `useAuthStore`, `useNotificationStore`, `useTicketStore`.
- No refleja `AIStatusPanel.tsx`.
- Simplifica demasiado la estructura real de `app`, `hooks`, `stores` y `lib`.

Prompt detallado:

```text
Generate a frontend file-tree infographic for the D4-Ticket AI project, using a clean modern pastel technical style with rounded cards and readable typography.

Real structure to show:
- frontend/src/app
  - page.tsx
  - (dashboard)/board/page.tsx
  - (dashboard)/tickets/[id]/page.tsx
  - (auth)/login/page.tsx
- frontend/src/components
  - tickets
  - board
  - ai-chat
  - notifications
  - layout
  - ui
  - ai/AIStatusPanel.tsx
- frontend/src/hooks
  - useTickets.ts
  - useWebSocket.ts
  - useNotifications.ts
  - useUsers.ts
  - useUIStore.ts
- frontend/src/stores
  - authStore.ts
  - notificationStore.ts
  - useSelectionStore.ts
- frontend/src/lib
  - api.ts
  - auth.ts
  - utils.ts
  - ticketRealtime.ts
  - attachmentUtils.ts
  - aiPreference.ts

Do not invent useAuthStore, useNotificationStore, or useTicketStore as file names. Make the infographic concise but technically faithful.
```

## image9.png

Estado:
- Se puede mantener con un ajuste opcional.

Observaciones:
- El flujo general es válido.
- `PostgresCheckpointer` puede refinarse para acercarlo al término real.

Prompt opcional:

```text
Edit this LangGraph ReAct agent diagram minimally. Keep the same layout and style, but rename "PostgresCheckpointer" to "AsyncPostgresSaver / PostgreSQL Checkpointer" for better technical fidelity. Everything else can remain conceptually the same.
```

## image10.png

Estado:
- Rehacer.

Errores detectados:
- Usa nombres de tools que no existen (`update_ticket_status`, `request_ticket_deletion`).
- Falta reflejar el flujo SSE real y los eventos de confirmación.
- No representa bien el papel del checkpointer ni de las tools actuales.

Prompt detallado:

```text
Generate a flowchart for the D4-Ticket AI LangGraph agent in a polished pastel technical infographic style. The flow must be faithful to the real project.

Main flow:
- Inicio de conversación
- Recibir mensaje del usuario
- Cargar historial del checkpointer PostgreSQL
- llm_node: razonar e invocar LLM
- Decisión: requiere herramienta?
- Si sí -> tool_node: ejecutar herramienta
- Registrar resultado
- Emitir eventos SSE
- Fin de turno / esperar entrada

Real SSE events to mention visually if possible:
- session
- token
- tool_start
- tool_call
- confirmation_required
- deletion_request_offer
- done

Real tools to list:
- query_tickets
- get_ticket
- get_ticket_history
- create_ticket
- change_status
- add_comment
- update_ticket
- find_users
- reassign_ticket
- search_knowledge
- ai_diagnose_ticket
- delete_ticket

Do not use fake names like update_ticket_status or request_ticket_deletion. Keep it precise, professional, and visually clear.
```
