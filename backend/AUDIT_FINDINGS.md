# Backend Audit — Logic Findings

> Snapshot tras la **segunda pasada de bug-fixing**. Cada hallazgo
> indica si fue **APLICADO**, **POSPUESTO** (con motivo) o resultó ser
> un **FALSO POSITIVO**.
>
> Severidad:
> - 🔴 **Bug** — incorrect behaviour or possible runtime error
> - 🟠 **Robustness / i18n** — fragility or UX consistency
> - 🟡 **Cleanup** — dead code, unused imports, style
> - 🔵 **Decision** — open question for the author

---

## ✅ Aplicado

### 🔴 `app/api/v1/auth.py` — Wrong exception caught on `ip_address`
Cambio: `except AddressValueError:` → `except ValueError:` con comentario
`# Why:` explicando que `ip_address()` lanza el `ValueError` padre cuando
recibe algo como `"unknown"`.

### 🟠 `app/api/v1/auth.py` — Hardened Google OAuth callback
- `is_success` check + `try/except` around `.json()` para los dos
  intercambios (`/token` y `/userinfo`).
- Una respuesta malformada de Google ahora produce un **400 controlado**
  en lugar de un 500 opaco.

### 🟠 i18n — Mensajes HTTP del backend traducidos a inglés
La UX muestra `response.data.detail` verbatim (verificado en
`frontend/src/app/(auth)/login/page.tsx:46` y
`frontend/src/components/tickets/TicketDetail.tsx:514`). Se ha unificado
todo a inglés:

- `auth.py` 403 — `"Access denied. Your email or domain is not in the allow-list."`
- `auth.py` 429 — `"Too many attempts. Please wait 15 minutes."`
- `auth.py` 401 — `"Invalid or unconfigured demo access code."`
- `tickets.py` 403 (delete) — `"Only the author can delete this ticket."`
- `ws.py` initial WS message — `"Initial state loaded"`

Y los fallbacks alineados en el frontend:

- `login/page.tsx:46` — `"Invalid access code."`
- `login/page.tsx:49` — `"Could not connect to the server."`

### 🟡 `app/api/v1/auth.py` — Cleanups
- Imports muertos: `Depends`, `get_db` eliminados.
- `logger = logging.getLogger(__name__)` movido debajo del bloque de
  imports (PEP 8).
- Bloque de imports ordenado (stdlib → third-party → app).

### 🟡 `app/api/v1/tickets.py` — Cleanups
- `_embed_ticket` (dead code) eliminado, junto con su import
  `generate_ticket_embedding` que solo él usaba.
- Import muerto `User` eliminado.
- `StreamingResponse` subido al header (estaba a media página).
- `history_service` añadido al import agregado del módulo; el
  `from app.services import history_service` interno de
  `get_ticket_history` ya no es necesario y se ha eliminado.

---

## ⚪ Falso positivo

### Doble `commit` en `request_ticket_deletion`
Anotación original incorrecta. `_create_notification` hace `flush()`,
no `commit()` (verificado en
`app/services/notification_service.py:91` con docstring explícito
*"flushed (not committed) so the caller decides the transaction
boundary"*). El `await db.commit()` posterior en el router es **el
único commit y es necesario**.

---

## ⏸️ Pospuesto (con motivo)

### 🟠 Ambigüedad `False` en `delete_comment` / `delete_attachment`
Refactor real (enum / excepciones dedicadas) abre superficie en dos
servicios y dos routers. El smell ya está documentado con un
`# Why:` en los routers
([comments.py:115](app/api/v1/comments.py),
[attachments.py:140](app/api/v1/attachments.py)).

### 🔵 Sobreescritura silenciosa del perfil OAuth en cada login
Aparenta ser comportamiento intencionado (el proyecto no tiene edición
local de perfil). Ya documentado con `# Why:` en
[auth.py](app/api/v1/auth.py).

### 🔵 `asyncio.create_task` sin done-callback
Cada coroutine fire-and-forget envuelve su cuerpo en `try/except` y
loguea (verificado en `scrape_and_index_url`,
`generate_ticket_embedding_task`, `_ingest_attachment_bg`). No hay
errores silenciados reales.

### Tests dedicados para bugs 1 y 2
No se añaden a la suite del proyecto (memoria y vídeo ya entregados).
Bocetos disponibles en el plan
`~/.claude/plans/act-a-como-un-ingeniero-soft-scott.md` si más adelante
se quieren blindar formalmente.
