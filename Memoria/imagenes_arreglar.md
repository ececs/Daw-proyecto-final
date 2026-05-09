# Imágenes a Arreglar

Documento de control para revisar y corregir las imágenes IA incluidas en la memoria de `D4-Ticket AI`.

Contexto base que deben respetar todas las imágenes:

- Proyecto: `D4-Ticket AI`
- Frontend: `Next.js 16`, `React 19`, `TypeScript`, `Zustand`
- Backend: `FastAPI`, `SQLAlchemy 2`, `Alembic`
- Base de datos: `PostgreSQL 16 + pgvector`
- Tiempo real: `WebSockets + Redis Pub/Sub` con fallback a `PostgreSQL NOTIFY`
- Storage: `Cloudflare R2` en producción, `MinIO` en local
- IA:
  - modelo principal final defendido: `GPT-4o-mini`
  - fallback: `Gemini 2.5 Flash`
  - embeddings: `gemini-embedding-2`
- Agente: `LangGraph` con memoria persistente usando `AsyncPostgresSaver` / checkpointer PostgreSQL
- Chat IA: `SSE`
- Sincronización de tickets y notificaciones: `WebSockets`
- RAG de adjuntos: opcional por archivo, activado con `use_for_rag`

## image1.png

Estado:
- Se puede dejar.

Errores detectados:
- No se detectan errores técnicos relevantes.
- Es una imagen decorativa/abstracta de portada.

Qué haría:
- Mantenerla tal cual.

Prompt si quisieras regenerarla:

```text
Create a polished editorial cover background for a technical project report titled "D4-Ticket AI". Dark navy background, luminous cyan network lines, glowing connection nodes, subtle futuristic UI panels in the distance, premium and professional style, elegant, minimal, no readable fake text, no logos, vertical A4 composition, clean center area reserved for title text.
```

## image2.png

Estado:
- Aprovechable.

Errores detectados:
- El bloque `CLIENT - Browser` es válido pero demasiado genérico.
- La imagen es muy conceptual; no es incorrecta, pero puede afinarse.
- Debe reflejar claramente:
  - `GPT-4o-mini` principal
  - `Gemini 2.5 Flash` fallback
  - embeddings separados con Google

Qué corregir:
- Si mantienes el diagrama, asegúrate de que:
  - `GPT-4o-mini` aparezca como principal
  - `Gemini 2.5 Flash` aparezca como fallback
  - no se sugiera que Gemini es el principal
- Opcional:
  - cambiar `CLIENT - Browser` por `Frontend (Next.js)`
  - cambiar `BACKEND - Server Card` por `Backend (FastAPI)`

Prompt de corrección:

```text
Edit this architecture diagram so it matches the final D4-Ticket AI stack exactly. Keep the same polished pastel infographic style. Update labels to:
- Frontend (Next.js 16 + React 19 + Zustand + WebSockets)
- Backend (FastAPI Routers + Domain Services)
- PostgreSQL + pgvector
- Redis Pub/Sub
- Cloudflare R2 (S3)
- Agent ReAct (LangGraph)
- GPT-4o-mini (Principal)
- Gemini 2.5 Flash (Fallback)
- gemini-embedding-2 for embeddings / semantic search
Do not invent extra systems. Clean typography, accurate arrows, professional software architecture infographic.
```

## image3.png

Estado:
- Hay que editarla.

Errores detectados:
- Si aparece `OpenAI API (fallback del agente)`, está desalineada con la decisión final.
- Debe quedar claro que:
  - `OpenAI API` se usa para `GPT-4o-mini` principal
  - `Google AI Studio` se usa para `Gemini 2.5 Flash` fallback y embeddings

Qué corregir:
- Cambiar el bloque de OpenAI a algo como:
  - `OpenAI API (GPT-4o-mini principal del agente)`
- Cambiar el bloque de Google a algo como:
  - `Google AI Studio (Gemini fallback + embeddings)`

Prompt de corrección:

```text
Edit this deployment/integration diagram while preserving the same visual style. Update the platform roles so they match the real project:
- Vercel (frontend)
- Railway (backend FastAPI + PostgreSQL)
- Cloudflare R2 (storage de adjuntos)
- OpenAI API (GPT-4o-mini principal del agente)
- Google AI Studio (Gemini 2.5 Flash fallback + gemini-embedding-2 embeddings)
Do not show OpenAI as fallback. Use accurate Spanish labels, premium clean infographic style, software architecture documentation look.
```

## image4.png

Estado:
- Se puede editar, pero tiene incoherencias.

Errores detectados:
- `Google Gemini 2.5` debería ser `Gemini 2.5 Flash`.
- La relación visual entre `LangGraph Engine` y `WebSockets` puede inducir a error.
- En el proyecto real:
  - el chat IA responde por `SSE`
  - los `WebSockets` se usan para tiempo real general, notificaciones y sincronización
- `Zustand State` es correcto como idea, pero el naming es algo genérico.

Qué corregir:
- Renombrar:
  - `Google Gemini 2.5` -> `Gemini 2.5 Flash`
  - `LangGraph Engine` -> `LangGraph Agent`
- Añadir o dejar claro:
  - `SSE` para streaming del chat IA
  - `WebSockets` para notificaciones/sincronización
- Evitar que el diagrama sugiera que LangGraph “vive” dentro del canal WebSocket.

Prompt de corrección:

```text
Edit this technical architecture diagram in the same visual style. Make it accurate for the D4-Ticket AI project:
- Next.js 16 frontend
- Zustand global state
- FastAPI routers
- Domain services
- LangGraph Agent
- PostgreSQL + pgvector
- Redis Pub/Sub
- Cloudflare R2
- OpenAI GPT-4o-mini as primary LLM
- Gemini 2.5 Flash as fallback LLM
- SSE for AI chat streaming
- WebSockets for real-time notifications and ticket synchronization
Avoid implying that LangGraph communicates through WebSockets for the chat response. Clean Spanish labels, accurate architecture.
```

## image5.png

Estado:
- Mejor rehacerla.

Errores detectados:
- Aparecen dos tablas `tickets`.
- `users.role` no existe.
- `comments.body` no coincide con el modelo real; en el proyecto es `content`.
- `notifications.read_status` no coincide; en el proyecto es `read`.
- `attachments` no representa bien los campos reales.
- `knowledge_chunks` no coincide con la estructura real.
- Falta `ticket_number`.
- Las relaciones no son fiables.

Estructura correcta simplificada que debería aparecer:

- `users`
  - `id`
  - `email`
  - `name`
  - `avatar_url`
  - `created_at`
- `tickets`
  - `id`
  - `ticket_number`
  - `title`
  - `description`
  - `status`
  - `priority`
  - `author_id`
  - `assignee_id`
  - `client_url`
  - `client_summary`
  - `embedding`
  - `created_at`
  - `updated_at`
- `comments`
  - `id`
  - `ticket_id`
  - `author_id`
  - `content`
  - `created_at`
- `attachments`
  - `id`
  - `ticket_id`
  - `uploader_id`
  - `filename`
  - `storage_key`
  - `size_bytes`
  - `mime_type`
  - `created_at`
  - `use_for_rag`
- `notifications`
  - `id`
  - `user_id`
  - `ticket_id`
  - `type`
  - `message`
  - `read`
  - `created_at`
- `ticket_history`
  - `id`
  - `ticket_id`
  - `actor_id`
  - `field`
  - `old_value`
  - `new_value`
  - `created_at`
- `knowledge_chunks`
  - `id`
  - `url`
  - `chunk_index`
  - `content`
  - `embedding`
  - `chunk_metadata`
  - `created_at`

Relaciones clave:
- `tickets.author_id -> users.id`
- `tickets.assignee_id -> users.id`
- `comments.ticket_id -> tickets.id`
- `comments.author_id -> users.id`
- `attachments.ticket_id -> tickets.id`
- `attachments.uploader_id -> users.id`
- `notifications.user_id -> users.id`
- `notifications.ticket_id -> tickets.id`
- `ticket_history.ticket_id -> tickets.id`
- `ticket_history.actor_id -> users.id`

Prompt de regeneración:

```text
Generate a clean, accurate entity-relationship diagram for the D4-Ticket AI project database. Use a premium pastel technical infographic style, readable typography, no invented tables, no duplicated entities.

Entities and fields:
- users: id, email, name, avatar_url, created_at
- tickets: id, ticket_number, title, description, status, priority, author_id, assignee_id, client_url, client_summary, embedding, created_at, updated_at
- comments: id, ticket_id, author_id, content, created_at
- attachments: id, ticket_id, uploader_id, filename, storage_key, size_bytes, mime_type, created_at, use_for_rag
- notifications: id, user_id, ticket_id, type, message, read, created_at
- ticket_history: id, ticket_id, actor_id, field, old_value, new_value, created_at
- knowledge_chunks: id, url, chunk_index, content, embedding, chunk_metadata, created_at

Show relationships clearly with crow’s foot notation where appropriate. Use English field names exactly as listed. Do not add role, password_hash, file_url, duplicated tickets, duplicated users, or fake analytics fields.
```

## image6.png

Estado:
- Mejor rehacerla.

Errores detectados:
- Repite `USERS`.
- Repite `COMMENTS`.
- Hay un bloque `COMMENTS` vacío.
- `password_hash` no corresponde con la autenticación real Google/demo.
- `priority` como `int` no representa tus enums reales.
- `knowledge_chunks` está inventada respecto al modelo real.
- `attachments.file_url` no coincide con `storage_key`.
- Falta `ticket_number`.

Qué hacer:
- No merece la pena parchearla.
- Mejor sustituirla por una sola versión correcta del esquema de base de datos y eliminar la redundancia con `image5`.

Prompt de regeneración:

```text
Create a polished database schema diagram for D4-Ticket AI, matching the real implementation exactly. Use a neat modern infographic style, soft blue background, clean rounded cards, but all technical content must be faithful.

Do not duplicate entities.
Do not include password_hash.
Do not include file_url.
Do not include fake relevance_score fields.
Do include ticket_number in tickets.
Do include use_for_rag in attachments.
Do include chunk_metadata in knowledge_chunks.

Real entities:
users, tickets, comments, attachments, notifications, ticket_history, knowledge_chunks

Use exact field names from the real schema and clear PK/FK labels.
```

## image7.png

Estado:
- Muy fácil de corregir.

Errores detectados:
- Pone `migrations/`.
- En tu proyecto real la carpeta es `alembic/`.

Qué corregir:
- Cambiar:
  - `migrations/` -> `alembic/`
  - subtítulo opcional: `Migraciones / revisiones Alembic`

Prompt de corrección:

```text
Edit this backend file-tree infographic while preserving style and layout. Replace the folder label "migrations/" with "alembic/". Keep the subtitle aligned with reality: "Migraciones y revisiones Alembic". Do not change the rest unless needed for visual balance.
```

## image8.png

Estado:
- Mejor corregir bastante o rehacer.

Errores detectados:
- `useAuthStore` no coincide con el repo actual.
- `useNotificationStore` no coincide con el repo actual.
- `useTicketStore` no coincide con el repo actual.
- La estructura mostrada simplifica demasiado algunos nombres y no refleja bien los ficheros reales.

Estructura real que conviene reflejar:

- `frontend/src/app/`
  - `page.tsx`
  - `(dashboard)/board/page.tsx`
  - `(dashboard)/tickets/[id]/page.tsx`
  - `(auth)/login/page.tsx`
- `frontend/src/components/`
  - `tickets/`
  - `board/`
  - `ai-chat/`
  - `notifications/`
  - `layout/`
  - `ui/`
  - `ai/AIStatusPanel.tsx`
- `frontend/src/hooks/`
  - `useTickets.ts`
  - `useWebSocket.ts`
  - `useNotifications.ts`
  - `useUsers.ts`
  - `useUIStore.ts`
- `frontend/src/stores/`
  - `authStore.ts`
  - `notificationStore.ts`
  - `useSelectionStore.ts`
- `frontend/src/lib/`
  - `api.ts`
  - `auth.ts`
  - `utils.ts`
  - `ticketRealtime.ts`
  - `attachmentUtils.ts`

Qué corregir:
- Sustituir stores inventados por los reales.
- Evitar decir que existe `useTicketStore` si no existe.
- Mostrar `AIStatusPanel` si quieres representar el panel de observabilidad.

Prompt de regeneración:

```text
Generate a frontend file-tree infographic for the D4-Ticket AI project, with accurate structure and clean modern design. Soft pastel technical style, rounded cards, readable typography.

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

Do not invent useAuthStore, useNotificationStore, or useTicketStore. Keep the infographic concise but technically faithful.
```

## image9.png

Estado:
- Se puede dejar.

Errores detectados:
- No graves.
- `PostgresCheckpointer` es aceptable como concepto, aunque la implementación real usa `AsyncPostgresSaver` / checkpointer PostgreSQL.

Qué corregir opcionalmente:
- Si quieres máxima fidelidad:
  - cambiar `PostgresCheckpointer` -> `AsyncPostgresSaver / Checkpointer PostgreSQL`

Prompt de corrección opcional:

```text
Edit this LangGraph ReAct agent diagram minimally. Keep the same layout and style, but rename "PostgresCheckpointer" to "AsyncPostgresSaver / Checkpointer PostgreSQL" for better technical fidelity. Everything else can remain conceptually the same.
```

## image10.png

Estado:
- Mejor rehacerla o editarla fuerte.

Errores detectados:
- Los nombres de tools no coinciden con el proyecto real.
- `update_ticket_status` no es la tool real.
- `request_ticket_deletion` no es la tool real.
- Faltan varias tools reales.
- El flujo es aceptable como idea, pero las etiquetas concretas no son fieles.

Tools reales del agente:

- `query_tickets`
- `get_ticket`
- `get_ticket_history`
- `create_ticket`
- `change_status`
- `add_comment`
- `update_ticket`
- `find_users`
- `reassign_ticket`
- `search_knowledge`
- `ai_diagnose_ticket`
- `delete_ticket`

Qué corregir:
- Cambiar los nombres falsos por los reales.
- Puedes mantener el flujo conceptual:
  - inicio
  - mensaje usuario
  - cargar historial/checkpointer
  - `llm_node`
  - decisión de tool call
  - `tool_node`
  - registrar resultado
  - emitir respuesta SSE
- Pero las listas de “herramientas disponibles” deben contener nombres reales.

Prompt de regeneración:

```text
Generate a flowchart for the D4-Ticket AI LangGraph agent in a clean pastel technical infographic style. The flow must be faithful to the real project.

Main flow:
- Inicio de conversación
- Recibir mensaje del usuario
- Cargar historial del checkpointer PostgreSQL
- llm_node: razonar e invocar LLM
- Decisión: requiere herramienta?
- Si sí -> tool_node: ejecutar herramienta
- Registrar resultado
- Volver a llm_node / siguiente iteración
- Generar respuesta SSE
- Fin de turno / esperar entrada

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

## Resumen de prioridad

### Se pueden dejar

- `image1.png`
- `image9.png`

### Corregir

- `image2.png`
- `image3.png`
- `image4.png`
- `image7.png`

### Mejor rehacer

- `image5.png`
- `image6.png`
- `image8.png`
- `image10.png`

## Orden recomendado de trabajo

Si quieres minimizar esfuerzo y eliminar los errores más peligrosos:

1. `image5.png`
2. `image10.png`
3. `image3.png`
4. `image7.png`
5. `image8.png`
6. `image6.png`
7. `image4.png`
8. `image2.png`
