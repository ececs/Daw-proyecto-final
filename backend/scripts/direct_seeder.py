import asyncio
import asyncpg
import uuid
import random
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables (.env from local or root directory)
load_dotenv()

# Target the local Docker Postgres container by default (exposed on port 5433).
# This prevents accidental data wipes on production even if the root .env is loaded.
LOCAL_DB_URL = "postgresql://postgres:postgres@localhost:5433/ticketai"

# Fetch configured URL with fallback to Docker local
DB_URL = os.getenv("DATABASE_URL", LOCAL_DB_URL)

# --- PRODUCTION SAFETY HARNESS ---
# If the detected URL points to a known Cloud/Production provider (Railway, Supabase, AWS),
# we explicitly override it and force the local URL to protect production data.
if any(cloud_provider in DB_URL for cloud_provider in ["rlwy.net", "railway", "supabase", "aws", "elephantsql"]):
    print("⚠️  [PRODUCTION GUARD] Detected cloud-hosted database in environment variables.")
    print(f"👉 Switching automatically to LOCAL DOCKER (localhost:5433) to prevent data loss.")
    DB_URL = LOCAL_DB_URL

# List of realistic virtual users and technical roles
VIRTUAL_USERS = [
    {"email": "usuario.demo@demo.local", "name": "Usuario Demo", "avatar_url": "https://api.dicebear.com/7.x/bottts/svg?seed=demo"},
    {"email": "sarah.connor@demo.local", "name": "Sarah Connor (Product Manager)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=sarah"},
    {"email": "linus.torvalds@demo.local", "name": "Linus Torvalds (Senior Backend)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=linus"},
    {"email": "ada.lovelace@demo.local", "name": "Ada Lovelace (Fullstack Developer)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=ada"},
    {"email": "grace.hopper@demo.local", "name": "Grace Hopper (QA Lead)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=grace"},
    {"email": "alan.turing@demo.local", "name": "Alan Turing (DevOps Architect)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=alan"},
    {"email": "margaret.hamilton@demo.local", "name": "Margaret Hamilton (Frontend Architect)", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=margaret"},
]

# High-quality predefined tickets in Spanish
TICKETS_PREDEFINIDOS = [
    {
        "title": "Rediseño de la página de inicio del portal de clientes",
        "description": (
            "El portal actual tiene una tasa de rebote del 68%. "
            "Necesitamos modernizar el diseño, mejorar la jerarquía visual "
            "y añadir CTAs más claros. Incluir versión mobile-first.\n\n"
            "**Criterios de aceptación:**\n"
            "- Nuevo hero section con video de fondo\n"
            "- Sección de métricas animadas\n"
            "- Testimonios con carrusel\n"
            "- Footer con mapa del sitio completo"
        ),
        "status": "open",
        "priority": "high",
    },
    {
        "title": "Integrar Stripe para pagos recurrentes",
        "description": (
            "Implementar Stripe Billing para suscripciones mensuales y anuales. "
            "El flujo debe soportar upgrades, downgrades y cancelaciones con "
            "período de gracia de 7 días.\n\n"
            "**Stack:** FastAPI + Stripe SDK Python + webhooks\n"
            "**Documentación:** https://stripe.com/docs/billing"
        ),
        "status": "open",
        "priority": "critical",
    },
    {
        "title": "Configurar alertas de error en Sentry",
        "description": (
            "Integrar Sentry en el backend y frontend. "
            "Configurar alertas por email cuando el error rate supere el 1% "
            "o cuando haya errores nuevos de tipo crítico."
        ),
        "status": "open",
        "priority": "medium",
    },
    {
        "title": "Migración de base de datos a PostgreSQL 16",
        "description": (
            "Migrar la instancia actual de PostgreSQL 14 a PostgreSQL 16. "
            "Beneficios: mejoras de rendimiento en queries complejas (~15%), "
            "nuevas funciones de JSON y soporte mejorado para particionado.\n\n"
            "**Plan de migración:**\n"
            "1. Snapshot de la DB actual\n"
            "2. Levantar nueva instancia PG 16 en producción\n"
            "3. pg_dump + pg_restore\n"
            "4. Verificar integridad con checksums\n"
            "5. Actualizar DATABASE_URL y reiniciar"
        ),
        "status": "in_progress",
        "priority": "high",
    },
    {
        "title": "Añadir tests E2E con Playwright",
        "description": (
            "Cubrir los flujos críticos de usuario con tests end-to-end:\n"
            "- Login con Google OAuth / Clave Demo\n"
            "- Crear y editar un ticket\n"
            "- Drag & drop en kanban\n"
            "- Subir adjunto\n"
            "- Recibir notificación en tiempo real\n\n"
            "Integrar en el pipeline de CI/CD de GitHub Actions."
        ),
        "status": "in_progress",
        "priority": "medium",
    },
    {
        "title": "Optimizar queries N+1 en el endpoint de tickets",
        "description": (
            "El endpoint GET /tickets está haciendo queries individuales para "
            "cargar author y assignee de cada ticket. Con 100+ tickets la "
            "latencia sube a >2s.\n\n"
            "**Fix:** Usar `selectinload` o `joinedload` de SQLAlchemy para "
            "cargar las relaciones en una sola query."
        ),
        "status": "in_progress",
        "priority": "high",
    },
    {
        "title": "Implementar rate limiting en endpoints públicos",
        "description": (
            "Añadir slowapi (wrapper de limits para FastAPI) para limitar:\n"
            "- POST /auth/google: 10 req/min por IP\n"
            "- POST /ai/chat: 20 req/min por usuario\n"
            "- GET /tickets: 100 req/min por usuario\n\n"
            "Retornar 429 Too Many Requests con header Retry-After."
        ),
        "status": "in_review",
        "priority": "medium",
    },
    {
        "title": "Dark mode en el dashboard principal",
        "description": (
            "Implementar tema oscuro usando Tailwind CSS dark: prefix y "
            "next-themes para persistir la preferencia del usuario.\n\n"
            "Respetar prefers-color-scheme del sistema operativo como valor "
            "por defecto. Añadir toggle en el header."
        ),
        "status": "in_review",
        "priority": "low",
    },
    {
        "title": "Setup inicial del proyecto — Docker Compose + CI/CD",
        "description": (
            "Configurar el entorno de desarrollo completo:\n"
            "- Docker Compose con FastAPI, PostgreSQL, MinIO\n"
            "- GitHub Actions para lint + tests en cada PR\n"
            "- Pre-commit hooks (ruff, mypy, prettier)\n"
            "- Variables de entorno documentadas en .env.example"
        ),
        "status": "closed",
        "priority": "high",
    },
    {
        "title": "Autenticación Google OAuth2 — flujo stateless",
        "description": (
            "Implementar login con Google sin estado de servidor:\n"
            "- Authlib reemplazado por httpx directo (sin SessionMiddleware)\n"
            "- JWT firmado con HS256, expiración configurable\n"
            "- Cookie segura para cross-domain auth\n"
            "- Middleware Next.js para proteger rutas privadas"
        ),
        "status": "closed",
        "priority": "critical",
    },
    {
        "title": "Notificaciones en tiempo real con WebSocket + PG NOTIFY",
        "description": (
            "Sistema de notificaciones push sin polling:\n"
            "- FastAPI WebSocket endpoint con autenticación por JWT\n"
            "- PostgreSQL LISTEN/NOTIFY para eventos de DB\n"
            "- Keepalive ping cada 30s para evitar timeout de red\n"
            "- Reconexión automática en el cliente con backoff"
        ),
        "status": "closed",
        "priority": "high",
    },
    {
        "title": "Corregir bug: cookie httpOnly bloquea logout",
        "description": (
            "El interceptor de axios no podía borrar una cookie httpOnly, "
            "causando un bucle redirect infinito al recibir un 401.\n\n"
            "**Fix:** Añadir ruta Next.js /api/auth/clear que borra la "
            "cookie server-side y redirige a /login."
        ),
        "status": "closed",
        "priority": "critical",
    },
]

# Random date generation utilities
def get_random_dates(days_back=30):
    seconds_back = random.randint(0, days_back * 24 * 60 * 60)
    created_at = datetime.now(timezone.utc) - timedelta(seconds=seconds_back)
    remaining_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
    updated_at = created_at + timedelta(seconds=random.randint(0, max(0, int(remaining_seconds))))
    return created_at, updated_at

async def direct_seed():
    # Check command line arguments for auto-population constraints
    only_if_empty = "--only-if-empty" in sys.argv

    print("🚀 Starting direct database seeding script...")
    print(f"🔗 Connecting to database...")
    
    try:
        clean_db_url = DB_URL.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(clean_db_url)
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        print("👉 Please ensure your database is running and accessible.")
        return

    try:
        # IF constraint mode: skip seeding completely if there are already tickets in the database
        if only_if_empty:
            count = await conn.fetchval("SELECT COUNT(*) FROM tickets")
            if count > 0:
                print(f"📊 [AUTO-SEED] Database already populated ({count} tickets found). Skipping auto-seeding.")
                return
            else:
                print("📊 [AUTO-SEED] Database is empty! Proceeding with automatic initial data seeding...")

        # 1. Setup virtual users
        print("👥 Configuring users and technical roles...")
        user_ids = []
        
        for u in VIRTUAL_USERS:
            res = await conn.fetchrow("SELECT id FROM users WHERE email = $1", u["email"])
            if not res:
                uid = str(uuid.uuid4())
                await conn.execute(
                    "INSERT INTO users (id, email, name, avatar_url, created_at) VALUES ($1, $2, $3, $4, NOW())",
                    uid, u["email"], u["name"], u["avatar_url"]
                )
                print(f"   ✅ Created virtual user: {u['name']} ({u['email']})")
                user_ids.append(uid)
            else:
                uid = str(res["id"])
                print(f"   ✔ Verified existing user: {u['name']}")
                user_ids.append(uid)

        evaluator_id = user_ids[0]

        # 2. Clean up old data (Safe when only_if_empty triggers, necessary for force re-seeding)
        print("🧹 Cleaning database tables to prevent collisions...")
        await conn.execute("DELETE FROM comments")
        await conn.execute("DELETE FROM ticket_history")
        await conn.execute("DELETE FROM tickets")
        print("   🧹 Flushed tickets, comments, and history tables.")

        # 3. Insert 12 high-quality predefined tickets with dispersed dates
        print("🎫 Inserting high-quality predefined tickets...")
        for i, t in enumerate(TICKETS_PREDEFINIDOS):
            tid = str(uuid.uuid4())
            created_at, updated_at = get_random_dates(days_back=45)
            assignee = random.choice(user_ids)
            
            await conn.execute(
                """
                INSERT INTO tickets (id, title, description, status, priority, author_id, assignee_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                tid, t["title"], t["description"], t["status"], t["priority"], evaluator_id, assignee, created_at, updated_at
            )
            
        # 4. Generate remaining 88 random tickets
        print("🎫 Generating and scattering 88 additional randomized tickets...")
        additional_titles = [
            "Optimizar rendimiento de DB para {feature}",
            "Corregir fuga de memoria en componente {module}",
            "Integrar {integration} en el workflow principal",
            "Configurar copias de seguridad automáticas para {service}",
            "Refactorizar lógica de validación de {module}",
            "Añadir telemetría detallada y monitorización de {feature}",
            "Resolver problemas de CORS en endpoint de {module}",
            "Implementar soporte de temas para {feature}",
            "Garantizar aislamiento multi-inquilino en {module}",
            "Optimizar latencia de red para peticiones de {service}"
        ]
        features = ["cuadro de mando de usuario", "flujo de pago", "logs en tiempo real", "subida de archivos", "autocompletado de IA", "tabla de tickets", "vista Kanban", "indexación de búsqueda"]
        modules = ["middleware de autenticación", "centro de notificaciones", "generador de embeddings", "sincronización WebSocket", "alertas de Sentry", "facturación con Stripe"]
        integrations = ["webhooks de Slack", "Cloudflare R2", "Google OAuth 2.0", "caché de Redis", "migraciones de Alembic"]
        services = ["base de datos PostgreSQL 16", "almacenamiento MinIO", "tareas en segundo plano FastAPI", "servidor Next.js"]
        statuses = ["open", "in_progress", "in_review", "closed"]
        priorities = ["low", "medium", "high", "critical"]

        for i in range(88):
            template = random.choice(additional_titles)
            title = template.format(
                feature=random.choice(features),
                module=random.choice(modules),
                integration=random.choice(integrations),
                service=random.choice(services)
            ) + f" (Auto-gen #{i+1})"
            
            desc = (
                f"Este es un ticket autogenerado realísticamente para pruebas de rendimiento, paginación y carga en volumen.\n\n"
                f"**Detalles de análisis:**\n"
                f"- Analizar métricas de rendimiento aplicadas a {random.choice(features)}.\n"
                f"- Verificar consistencia en la integración de {random.choice(integrations)}.\n"
                f"- Asegurar total compatibilidad con {random.choice(services)} en el entorno de desarrollo."
            )
            tid = str(uuid.uuid4())
            created_at, updated_at = get_random_dates(days_back=60)
            status = random.choice(statuses)
            priority = random.choice(priorities)
            assignee = random.choice(user_ids)
            
            await conn.execute(
                """
                INSERT INTO tickets (id, title, description, status, priority, author_id, assignee_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                tid, title, desc, status, priority, evaluator_id, assignee, created_at, updated_at
            )

        print("\n🎉 Database seeding completed successfully!")
        print("📊 Seeding Metrics Summary:")
        print(f"   - Users created/verified: {len(user_ids)}")
        print(f"   - Total tickets generated: 100 (12 premium + 88 dynamic)")
        print("   - Temporal distribution: Spread randomized between 1 and 60 days in the past.")
        print("\n👉 System is now fully ready to demonstrate charts, hybrid search, and complete history states.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(direct_seed())
