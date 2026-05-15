# Frontend Audit — Logic Findings

> Snapshot tras la pasada de **i18n cleanup** que siguió al audit
> académico. Cada hallazgo indica si está **APLICADO** o **POSPUESTO**
> (con motivo).
>
> Severidad:
> - 🔴 **Bug** — incorrect behaviour or possible runtime error.
> - 🟠 **Robustness / i18n** — fragility or UX consistency.
> - 🟡 **Cleanup** — dead code, redundant comments, style.
> - 🔵 **Decision** — open question for the author.

---

## ✅ Aplicado

### 🟠 Stale Spanish handshake guard in `useWebSocket` *(bug fix)*
**Location:** [src/hooks/useWebSocket.ts](src/hooks/useWebSocket.ts).
El filtro comparaba `message !== "Estado inicial cargado"` pero el
backend emitía `"Initial state loaded"` desde la i18n del backend.
Resultado anterior: un toast vacío "Aviso del Sistema" en cada
(re)conexión. Sincronizado al literal nuevo y reforzado con un
comentario `# Why:` que vincula el contrato al
`backend/app/api/v1/ws.py`. Test `useWebSocket.test.ts` actualizado
en lockstep.

### 🟠 Spanish UI strings → English
Cadenas visibles al usuario unificadas a inglés para evitar pantallas
mixtas ES/EN:

| Archivo | Cambios |
|---|---|
| `src/hooks/useWebSocket.ts` | toast `New notification` / `You have a new update.` / `System notice` |
| `src/components/board/KanbanBoard.tsx` | toast `Status change failed` / `Could not move the ticket. Please try again.` |
| `src/components/tickets/TicketForm.tsx` | aria `Close`; labels `View extracted web analysis`, `Indexed snippet for RAG`, `Client summary / business context`; hint `Triggers an automatic scan to improve the AI diagnosis.`; placeholder `e.g. Banking client, uses GCP/K8s, very technical...` |
| `src/components/tickets/TicketTable.tsx` | aria `Search tickets`, `Filter by status`, `Filter by priority`, `Filter by assignee`, `Select all`/`Deselect all`, `Select ticket`/`Deselect ticket` |
| `src/components/ai-chat/ChatSidebar.tsx` | `Server error.`, `Error: could not connect to the AI (… "Something went wrong").`, aria `New conversation`, `Close chat` |
| `src/app/(auth)/login/page.tsx` | aria `Sign in with Google`, `Demo access code` |
| `src/hooks/useWebSocket.test.ts` | 3 asserts/fixtures sincronizados con los nuevos literales |

**Verificación** — `tsc --noEmit` ✅, `eslint` (preexistente 1 err +
1 warn, sin cambios) ✅, `vitest` 58/58 ✅, `pytest` 212/212 ✅.

---

## ⏸️ Pospuesto (con motivo)

### 🟡 Liar return type in `notificationStore`
`markAsRead` / `markAllAsRead` declaradas `() => void` pero
implementadas `async`. Cambio de firma público a `Promise<void>`
requiere revisar todos los call sites para confirmar que ninguno
los trata como sincrónicos. Limpieza separada.

### 🟡 Compatibilidad legacy `"TICKET_DELETED"` en mayúsculas
Solo el caso lowercase se emite hoy desde el backend (verificable en
`notification_service.broadcast_global_event`). El test
`"TICKET_DELETED uppercase alias is handled for backwards
compatibility"` documenta y prueba el alias. Eliminar requiere
también borrar el test → cambio aparte.

### 🔵 Welcome message del `ChatSidebar`
Hard-coded en inglés mientras el agente responde multilingüe. Es
una decisión de UX que el tribunal puede valorar como aceptable.

### 🔵 UI primitives shadcn intactas
`badge.tsx`, `toast.tsx`, `toaster.tsx` conservan el template
upstream con un docstring mínimo añadido por el audit. Cualquier
divergencia del template requiere decisión explícita.

### 🔵 Sistema i18n formal (next-intl / react-i18next)
Fuera del alcance del PFC. Si el proyecto va a mantenerse con
público multilingüe, conviene migrar a un catálogo de mensajes
en lugar de literales inline.

---

## ⚪ Falso positivo / aclaraciones

- El fixture `"Mantenimiento programado en 10 minutos"` en
  `useWebSocket.test.ts` se mantiene en español porque representa un
  *cuerpo de mensaje* libre proveniente del backend, no una etiqueta
  de UI controlada por el frontend.
- Los warnings preexistentes de ESLint (`useTickets.ts:158`,
  `TicketDetail.tsx:413`) **no se introdujeron en esta pasada**
  (verificado por diff sobre HEAD limpio antes del cleanup); su
  resolución es un cambio aparte.
