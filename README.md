# PartSelect Chat Agent

An AI-powered chat assistant for the PartSelect e-commerce website, specializing in **refrigerator and dishwasher** replacement parts. Built as a two-service architecture with a Next.js frontend and FastAPI backend.

View slides [here](https://sruthi-sk.github.io/tool-augmented-ecommerce-agent/)

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4 | Split-panel chat UI with rich detail components |
| **Backend** | FastAPI, Pydantic, Uvicorn | API server, request validation, SSE streaming |
| **Database** | SQLite + aiosqlite | Structured product index (parts, compatibility, symptoms, installation steps) |
| **Full-text search** | SQLite FTS5 (Porter stemming) | Keyword search over parts and repair guide content |
| **Vector search** | FAISS (faiss-cpu) + OpenAI `text-embedding-3-small` | Semantic symptom routing and help chunk retrieval |
| **LLM orchestration** | OpenAI GPT-4o (default), Anthropic Claude (swap via env var) | Two-pass tool routing + response composition |
| **Web scraping** | [Crawl4AI](https://github.com/unclecode/crawl4ai) (Playwright-backed), BeautifulSoup | Offline batch ingestion + live compatibility fallback |
| **Testing** | pytest, pytest-asyncio | Unit and integration tests |

## Architecture

```

┌─────────────────────────┐       ┌─────────────────────────────────┐
│   Next.js Frontend      │       │   FastAPI Backend               │
│                         │       │                                 │
│  ┌───────┐ ┌─────────┐  │ POST  │  ┌────────────────┐             │
│  │ Chat  │ │ Detail  │  │──────►│  │ Preprocessor   │ scope check │
│  │ Panel │ │ Panel   │  │       │  │ (deterministic)│ + entities  │
│  └───────┘ └─────────┘  │       │  └──────┬─────────┘             │
│                         │       │         ▼                       │
│  Split panel layout     │       │  ┌───────────────┐              │
│  - Chat (left)          │◄──────│  │ LLM Provider  │ tool routing │
│  - Context (right)      │  JSON │  │(OpenAI/Claude)│              │
└─────────────────────────┘       │  └──────┬────────┘              │
                                  │         ▼                       │
                                  │  ┌──────────────┐               │
                                  │  │ Tool Registry│ 6 tools       │
                                  │  └──────┬───────┘               │
                                  │         ▼                       │
                                  │  ┌───────────────────────────┐  │
                                  │  │ KnowledgeService          │  │
                                  │  │  structured SQLite index  │  │
                                  │  │  + FAISS semantic search  │  │
                                  │  └───────────────────────────┘  │
                                  └─────────────────────────────────┘
```

## Features

| Capability | Tool | Detail Panel |
|---|---|---|
| Part search | `search_parts` | Search results list (filters by model when provided) |
| Part details | `get_part_details` | Product card with price, stock, description |
| Compatibility check | `check_compatibility` | Green/red/amber compatibility indicator (3 states) |
| Installation guide | `get_installation_guide` | Step-by-step instructions |
| Troubleshooting | `diagnose_symptom` | Causes ranked by likelihood |
| Model overview | `lookup_model` | Brand, appliance type, common symptoms, part categories |

## Design

### Agentic Architecture
- **LLM as router, not truth source** — The LLM picks which tool to call and composes the response, but all product facts come from the pre-indexed SQLite store. This prevents hallucinated prices, part numbers, or compatibility claims.
- **Deterministic pre-processor** — Regex + keyword scope check runs before any LLM call. Enforces the "refrigerator and dishwasher only" constraint without spending tokens, and extracts entities (part numbers, model numbers, brands) for session state.
- **Two-pass LLM flow** — First call selects a tool via function calling. Second call composes a natural language response from the structured tool result. Separates routing from generation. Up to 3 tool calls per turn (configurable via `MAX_TOOL_CALLS_PER_TURN` env var), enabling chains like `search → compatibility` in a single conversation turn.
- **Model-aware search with live fallback** — When the user provides a model number, `search_parts` filters results to parts compatible with that model via the `part_compatibility` table. If the local index returns 0 results (incomplete part coverage), the system falls back to scraping the PartSelect model parts page via crawl4ai. The system prompt instructs the LLM to always pass the model number when known, and to confirm the fit with `check_compatibility` before recommending a part.
- **Model overview** — `lookup_model` scrapes the PartSelect model page to extract brand, appliance type, common symptoms, part categories, and section headings. The `ModelOverview` component displays this in the right panel when users ask about a specific model number.
- **Grounding / validation layer** — After the LLM composes a response, a deterministic validator rewrites it if the stated facts (part number, compatibility, URL) don't match `detail_data`. A second pass deterministically appends any important URLs (model page links, similar models) that the LLM omitted, so users always see actionable links. No LLM judge loop.
- **Provider-agnostic** — `LLMProvider` ABC with OpenAI (default) and Anthropic adapters. Tool schemas auto-generate in both formats from a single registration. Swap with one env var: `LLM_PROVIDER=anthropic`.

### Data Layer
Product data is **scraped offline and stored in SQLite** before runtime. PartSelect blocks plain HTTP clients (403), so scraping at query time would require a Playwright browser per request (5–10s latency). The offline approach moves that cost to ingestion time.

- **Offline ingestion** — `backend/ingestion/crawl_partselect.py` uses [Crawl4AI](https://github.com/unclecode/crawl4ai) (Playwright-backed) to crawl PartSelect through hierarchical navigation: category pages → brand pages → related sub-category pages → individual part detail pages. Discovers thousands of parts per category. Extracts 16+ fields per part. Also scrapes repair guide pages and stores them as searchable help chunks.
- **Live fallback with graceful degradation** — For compatibility checks where the model isn't in the local index (PartSelect paginates models), the system attempts a live browser check via crawl4ai. When live scraping succeeds, results are cached in-memory with per-key deduplication and persisted into SQLite for future local hits. When PartSelect's bot detection blocks the request (403), the system gracefully degrades: it tells the user live scraping failed and provides a direct PartSelect link to check compatibility manually. Only definitive results (compatible/incompatible) are cached — inconclusive results are retried on the next request. Similarly, model-filtered searches fall back to live scraping of the model parts page when the local index has incomplete part coverage.
- **FAISS semantic search** — Symptom data and repair guides are embedded into a FAISS index at ingestion time. At query time, natural-language symptoms ("my fridge makes a grinding noise") are routed to the correct structured `symptom_key` via cosine similarity, then the structured store provides grounded causes and part recommendations. Search uses adaptive over-fetch with retry to guarantee `k` results even with selective filters.
- **KnowledgeService** — Single interface used by all 6 tools. Combines structured SQLite queries with FAISS semantic search. Tools never interact with storage directly — the underlying storage can be replaced without touching tool code.

**Schema:**
```
parts                    — core product facts (16+ fields per part)
models                   — appliance model records
part_compatibility       — part ↔ model many-to-many
part_installation_steps  — ordered installation narratives per part
part_symptoms            — symptom tags per part
troubleshooting_causes   — appliance+symptom → likely cause + part type
help_chunks              — scraped repair guide content, keyed by symptom_key
help_chunks_fts / parts_fts — FTS5 virtual tables for keyword search
```

### User Experience
- **PartSelect branding** — UI uses PartSelect's blue (#003DA5) color scheme, logo treatment, and typography.
- **Split panel layout** — Chat on the left, contextual detail panel on the right. The panel renders product cards, compatibility results, installation guides, troubleshooting flows, or search results based on `response_type`.
- **Contextual suggested actions** — Backend returns suggested next steps (e.g., "Check compatibility", "How to install this part") as clickable chips that guide users through the natural transaction flow: symptom → diagnosis → part → compatibility → installation.
- **Narrow questions** — when a model number is missing, the agent asks only "What's your model number?" instead of broad multi-field questions. Minimizes friction at the highest-abandonment point.
- **Constructive refusals** — out-of-scope responses redirect: *"I can only help with refrigerator and dishwasher parts. Could you ask about finding parts, compatibility, installation, or troubleshooting?"*
- **Source citations** — every factual response includes a PartSelect link. Users click through to verify and purchase.

### Accuracy and Efficiency

**Three layers of fact correctness:**
1. **Data quality at ingestion** — every record stores a verified `source_url` tracing back to a real PartSelect page.
2. **LLM instructed not to speculate** — system prompt: *"NEVER invent or guess product information. Only use data returned by your tools."*
3. **Post-generation grounding** — a deterministic validator rewrites hallucinated part numbers, prices, or URLs before the response leaves the backend.

**Efficiency:** Scope rejections cost ~0ms (preprocessor, no LLM call). All tools except live compatibility fallback run against the local SQLite index with sub-10ms execution. FTS5 with Porter stemming handles keyword search with inflection tolerance. Session history capped at 20 messages to bound token usage.

## Project Structure

```
case-study-main/          # Next.js frontend
  src/
    app/page.tsx           # Split panel layout + state management
    components/            # ChatPanel, DetailPanel, ProductCard, etc.
    lib/api.ts             # Backend API client + session management
    types/chat.ts          # Shared TypeScript interfaces

backend/                   # FastAPI backend
  main.py                  # App entry, lifespan, /api/chat endpoint
  config.py                # Environment config
  agent/
    orchestrator.py        # Preprocess → LLM → tool → compose pipeline
    preprocessor.py        # Deterministic scope check + entity extraction
    session.py             # Session state with SessionStore ABC
    validation.py          # Deterministic grounding/rewrite layer
  providers/
    base.py                # LLMProvider ABC, ToolCall, LLMResponse
    openai_provider.py     # OpenAI function calling (default)
    claude_provider.py     # Anthropic tool_use
  tools/
    registry.py            # Decorator-based registration, multi-provider schemas
    search.py              # search_parts
    part_details.py        # get_part_details
    compatibility.py       # check_compatibility
    installation.py        # get_installation_guide
    symptom.py             # diagnose_symptom
    model.py               # lookup_model
  index/
    schema.sql             # SQLite schema for structured truth store
    structured_store.py    # CRUD + query layer over SQLite
    help_vector_store.py   # FAISS semantic search + FTS fallback
    knowledge_service.py   # Unified interface used by all tools
  ingestion/
    crawl_partselect.py    # Offline Crawl4AI-based batch ingestion: parts + repair guides
    build_partselect_index.py  # Schema init + troubleshooting KB bootstrap
  retrieval/
    scraper.py             # HTML parser (used by ingestion, not at runtime)
  tests/                   # pytest test suite
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- An OpenAI API key (or Anthropic key if using Claude)

### 1. Build the index (one-time)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Crawl PartSelect and populate partselect_index.db
python -m ingestion.crawl_partselect --limit 50 --concurrency 3
```

This discovers parts by following brand → sub-category → part detail page links (up to 50 parts per category). Also scrapes all available repair guide pages and builds a FAISS semantic index over the help content. Use a higher `--limit` (e.g., 500 or 5000) to index more parts. Re-run any time to refresh data; already-indexed parts are skipped automatically.

### 2. Start the backend

```bash
cd backend
cp .env.example .env   # add your OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd case-study-main
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Example Queries

1. **Part lookup**: "Tell me about PS11752778"
2. **Compatibility check**: "Is part PS11752778 compatible with WDT780SAEM1?"
3. **Troubleshooting**: "My Whirlpool fridge ice maker isn't working"
3b. **Semantic symptom**: "My refrigerator makes a grinding noise when dispensing ice" (FAISS routes to correct symptom)
4. **Installation**: "How do I install a dishwasher heating element?"
5. **Part search**: "Find me a dishwasher spray arm"
5b. **Model-filtered search**: "Find me a crisper pan for my 10650022211 Kenmore refrigerator" (filters results to compatible parts, falls back to live scraping if local DB is sparse)
6. **Model overview**: "Tell me about model 10650022211" → brand, appliance type, common symptoms, part categories
7. **Scope guardrail**: "What's the weather?" → polite refusal
7. **Multi-turn**: Give a model number, then ask "is it compatible?" (uses session state)

## Testing

```bash
cd backend
# Unit tests (no network)
pytest -v
# Live ingestion tests (requires Playwright + internet)
pytest -m live -v
```

## Extensibility

- **Add a new tool**: Decorate a function with `@registry.register()` in `backend/tools/` — schemas auto-generate for OpenAI and Anthropic. The orchestrator picks it up automatically; no routing changes needed.
- **Add an LLM provider**: Implement `LLMProvider` ABC in `backend/providers/`, set `LLM_PROVIDER=yourprovider`. Tool schemas auto-translate per provider.
- **Add an appliance type**: Three config changes — add keywords to `preprocessor.py`, category URL to `CATEGORY_URLS` in `crawl_partselect.py`, repair index URL to `REPAIR_INDEXES`. The `appliance_type` field threads through the entire stack automatically.
- **Persistent sessions**: Swap `InMemorySessionStore` with Redis/SQLite via the same interface.
- **Expand the index**: Re-run `crawl_partselect.py` with a higher `--limit`. Already-indexed parts are skipped automatically.

## Scalability

### Horizontal Scaling
- **Stateless request handling** — each API call carries a `session_id`; supports multi-instance deployments with a persistent `SessionStore` (Redis).
- **Read-only index** — SQLite is read-only at runtime, shareable via mounted volume or replaceable with Postgres through the same `KnowledgeService` interface.

### Scaling to All Products 

**Ingestion:** Move to a task queue (Celery/RQ) with multiple browser workers and switch from SQLite to Postgres.

**Retrieval:** FTS5 scales to ~100K rows  → then use Postgres (tsvector + GIN). FAISS flat index is O(n) — use IVF-PQ or a dedicated ANN service at scale. Symptom embeddings scale linearly with unique `(symptom_key, appliance_type)` pairs — likely <10K even at full catalog.

