# 🏛️ System Architecture: Ticket AI (D4-Ticket AI)

This document provides an exhaustive technical overview of the software architecture, transactional pipelines, and distributed workflows designed for the **D4-Ticket AI** graduation project. It outlines the decoupled integration between the Frontend ecosystem (React/Next.js), the reactive API Gateway (FastAPI), and the underlying Artificial Intelligence & Persistence layers.

---

## 📊 1. High-Level Topology (C4 System Context)

The following architecture diagram illustrates the runtime deployment topology and functional boundaries:

```mermaid
graph TB
    subgraph Client ["🌐 Client Tier (Frontend)"]
        UI[Next.js 16+ App Router]
        State[Zustand State Manager]
        WS_Client[WebSocket Client]
        UI --> State
        UI --> WS_Client
    end

    subgraph Gateway ["⚙️ API Gateway & Business Logic"]
        FastAPI[FastAPI App - Python 3.12]
        Auth[Google OAuth2 & Stateless JWT]
        Router[REST & SSE Routers]
        WS_Mgr[WebSocket Manager]
        
        FastAPI --> Auth
        FastAPI --> Router
        FastAPI --> WS_Mgr
    end

    subgraph AI ["🧠 Artificial Intelligence & RAG Engines"]
        LG[LangGraph Orchestrator]
        RAG[RAG Semantic Retrieval]
        LLM[LLMs: OpenAI / Gemini]
        Metrics[Telemetry: AI Run Tracker]
        
        LG --> RAG
        LG --> LLM
        LG --> Metrics
    end

    subgraph Persistence ["💾 Data & Real-Time Persistence"]
        DB[(PostgreSQL 16 + pgvector)]
        Redis[(Redis Cache & PubSub)]
        S3[(MinIO / Cloudflare R2)]
    end

    %% Communications
    UI -- HTTPS / REST --> Router
    WS_Client -- WebSocket (WSS) --> WS_Mgr
    UI -- Event Streams (SSE) --> LG

    Router --> DB
    Router --> Redis
    Router --> S3
    
    LG -- Vector Distance Search --> DB
    LG -- Thread Checkpoints --> DB
    
    WS_Mgr -- SUBSCRIBE --> Redis
    DB -- LISTEN / NOTIFY --> FastAPI
```

---

## 🔐 2. Authentication Pipeline (Stateless Google OAuth 2.0)

The system implements an industrialized 3-legged OAuth 2.0 authorization grant flow. It leverages cryptographically signed `HttpOnly` cookies for state validation to mitigate Cross-Site Request Forgery (CSRF) threat vectors.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant API as FastAPI Backend
    participant Google as Google Identity Provider

    User->>Browser: Clicks "Sign in with Google"
    Browser->>API: GET /api/v1/auth/google
    Note over API: Generates random cryptographic state
    API-->>Browser: Set-Cookie: oauth_state (HttpOnly, Lax)<br>Redirect URL (Google Auth + state)
    Browser->>Google: Grant User Permissions
    Google-->>Browser: Redirect with ?code=XXX&state=YYY
    Browser->>API: GET /api/v1/auth/callback?code=XXX&state=YYY
    Note over API: Verifies incoming state matches stored cookie value
    API->>Google: POST /token (Authorization Code Exchange)
    Google-->>API: Returns access_token & IdToken claims
    Note over API: Evaluates domain whitelisting & persists/merges User record
    Note over API: Generates signed HS256 JWT holding user context
    API-->>Browser: Redirects to Frontend with ?token=JWT
    Note over Browser: Stores JWT payload in LocalStorage / React Context
```

---

## ⚡ 3. Real-Time Communication Layer (Reactive WebSockets)

To achieve zero-latency updates across multiple concurrent operators (e.g., rendering live ticket cards instantly inside the Kanban view), the platform implements an event-driven Publish/Subscribe pattern bound to **PostgreSQL LISTEN/NOTIFY**.

```mermaid
sequenceDiagram
    autonumber
    actor OpA as Operator A
    participant FrontendA as UI Client A
    participant DB as PostgreSQL (Database Triggers)
    participant API as FastAPI (Asyncpg Worker Pool)
    participant FrontendB as UI Client B (Subscribed)
    actor OpB as Operator B

    OpA->>FrontendA: Submits Ticket / Appends Comment
    FrontendA->>API: POST /api/v1/tickets (REST)
    API->>DB: INSERT INTO ticket (...)
    Note over DB: Triggers pg_notify('notifications', JSON_PAYLOAD)
    DB-->>API: Asynchronous connection interrupt (AsyncPG listen loop)
    Note over API: Evaluates frame routing (specific UserID or Global '*')
    API-->>FrontendB: Dispatches WebSocket Frame: { type: "TICKET_CREATED", data: {...} }
    Note over FrontendB: Zustand refreshes state reactively without polling
    FrontendB-->>OpB: Renders dynamic ticket card instantly on viewport
```

---

## 🧠 4. Intelligent Co-Pilot: Hybrid RAG & Agentic Workflows

The core AI engine assists operators in troubleshooting complex tickets by combining precise lexical retrieval with vector-based conceptual semantics.

### Retrieval Engine: Hybrid Search via Reciprocal Rank Fusion (RRF)
Raw vector similarity searches often fail on exact names, configuration flags, or system port numbers. To guarantee robust recall, the backend orchestrates:
1.  **Semantic Vector Search**: Embeds incoming user queries via external vectorizers and computes cosine distance inside `pgvector`.
2.  **Lexical Search (BM25/Full-Text)**: Executes traditional, weighted full-text index lookups inside Postgres.
3.  **Reciprocal Rank Fusion**: Consumes both ranked lists and applies a weighted Reciprocal Rank Fusion equation to provide an industrialized, highly accurate fused set of document chunks.

### Cyclic State Graph (LangGraph Orchestration)
Rather than employing a basic, sequential text-completion interface, the chat co-pilot is modeled as a **Cyclic Stateful Action-Selection Graph**:

```mermaid
graph LR
    Start([Start]) --> Input[Context Integrator]
    Input --> Agent{Should Execute Tool?}
    
    Agent -- Yes --> ToolCall[Tool Runtime Dispatcher]
    ToolCall -- RAG Retriever --> Knowledge[(Vector Chunks)]
    ToolCall -- DB Mutator --> SQL[(Postgres DB)]
    ToolCall -- Scraping Worker --> Internet[External Target URL]
    
    Knowledge --> Agent
    SQL --> Agent
    Internet --> Agent
    
    Agent -- No / Halt --> Output[SSE Token Streaming]
    Output --> End([End])
```

### Telemetry & Economic Modeling
Every operational runtime trace is logged inside the database via a unified `AIRunTracker` module:
*   Aggregates actual input/output token counters on terminal connection closures.
*   Applies specific cost-per-million metrics to estimate the absolute USD transaction cost for each LLM invocation.
*   Pairs runtime stats with end-user `AIFeedback` payloads for offline evaluation and prompt engineering cycles.

---

## 📁 5. Project Directory Layout (Professional Monorepo)

```text
📂 DAW-PROYECTO-FINAL
├── 📂 backend/                  # FastAPI Enterprise Clean Architecture (Hexagonal-Lite)
│   ├── 📂 app/
│   │   ├── 📂 ai/               # Agentic Workflows, LangGraph Checkpointers, & Observability
│   │   ├── 📂 api/              # API Gateway controllers (REST, SSE, WebSockets)
│   │   ├── 📂 core/             # JWT Security, PydanticSettings Config, & WebSocketManager
│   │   ├── 📂 db/               # Asynchronous SQLAlchemy Engine & Session Factories
│   │   ├── 📂 models/           # Declarative Domain Models (SQLAlchemy Mappings)
│   │   ├── 📂 schemas/          # Typed Input/Output Data Transfer Objects (Pydantic)
│   │   └── 📂 services/         # Domain Logic Modules (Cache, RAG, Scrapers, Notifications)
│   └── 📂 tests/                # Integration Pytest Suite (212 test cases, Zero Regressions)
│
└── 📂 frontend/                 # Next.js Enterprise Component Topology
    ├── 📂 e2e/                  # Playwright End-to-End Browser Test Specs
    └── 📂 src/
        ├── 📂 app/              # App Router Hierarchy (Pages, Dynamic Slugs, Global Layouts)
        ├── 📂 components/       # Atomized React UI Modules (Kanban Board, AI Lateral Drawers)
        ├── 📂 hooks/            # Stateful Enterprise Custom Hooks (useAuth, useWS)
        ├── 📂 lib/              # External Clients (Axios Singleton Instance) & Utility Helpers
        └── 📂 store/            # Zustand State Slices (Global Responsive UI Synchronization)
```
