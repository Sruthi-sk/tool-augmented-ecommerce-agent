# PartSelect Chat Agent

An AI-powered chat assistant for the PartSelect e-commerce website, specializing in **refrigerator and dishwasher** replacement parts. Built as a two-service architecture with a Next.js frontend and FastAPI backend.

## Architecture

```
┌─────────────────────────┐       ┌──────────────────────────────────┐
│   Next.js Frontend      │       │   FastAPI Backend                │
│                         │       │                                  │
│  ┌───────┐ ┌─────────┐ │ POST  │  ┌──────────────┐               │
│  │ Chat  │ │ Detail  │ │──────►│  │ Preprocessor │ scope check   │
│  │ Panel │ │ Panel   │ │       │  │ (deterministic)│ + entities   │
│  └───────┘ └─────────┘ │       │  └──────┬───────┘               │
│                         │       │         ▼                        │
│  Split panel layout     │       │  ┌──────────────┐               │
│  - Chat (left)          │◄──────│  │ LLM Provider │ tool routing  │
│  - Context (right)      │  JSON │  │ (OpenAI/Claude)              │
└─────────────────────────┘       │  └──────┬───────┘               │
                                  │         ▼                        │
                                  │  ┌──────────────┐               │
                                  │  │ Tool Registry│ 5 tools       │
                                  │  └──────┬───────┘               │
                                  │         ▼                        │
                                  │  ┌───────────────────────────┐  │
                                  │  │ KnowledgeService          │  │
                                  │  │  structured SQLite index  │  │
                                  │  │  + FTS help chunks        │  │
                                  │  └───────────────────────────┘  │
                                  └──────────────────────────────────┘
```

## Key Design Decisions

### Agentic Architecture
- **LLM as router, not truth source** — The LLM picks which tool to call and composes the response, but all product facts come from the pre-indexed SQLite store. This prevents hallucinated prices, part numbers, or compatibility claims.
- **Deterministic pre-processor** — Regex + keyword scope check runs before any LLM call. Enforces the "refrigerator and dishwasher only" constraint without spending tokens, and extracts entities (part numbers, model numbers, brands) for session state.
- **Two-pass LLM flow** — First call selects a tool via function calling. Second call composes a natural language response from the structured tool result. Separates routing from generation.
- **Grounding / validation layer** — After the LLM composes a response, a deterministic validator rewrites it if the stated facts (part number, compatibility, URL) don't match `detail_data`. No LLM judge loop.
- **Provider-agnostic** — `LLMProvider` ABC with OpenAI (default) and Anthropic adapters. Tool schemas auto-generate in both formats from a single registration. Swap with one env var: `LLM_PROVIDER=anthropic`.

### Data Layer: Pre-indexed Structured Truth
Product data is **scraped offline and stored in SQLite** before runtime. The backend never scrapes at query time.

- **Offline ingestion** — `backend/ingestion/crawl_partselect.py` uses [Crawl4AI](https://github.com/unclecode/crawl4ai) (Playwright-backed) to crawl PartSelect category pages, bypass bot detection, and extract structured part data into `partselect_index.db`. The same script also scrapes PartSelect repair guide pages and stores them as searchable help chunks.
- **Structured store** — `backend/index/structured_store.py` wraps the SQLite tables (`parts`, `part_compatibility`, `part_installation_steps`, `part_symptoms`, `models`).
- **Repair guide index** — Each PartSelect repair guide (e.g. `/Repair/Refrigerator/Not-Making-Ice/`) is scraped and stored in `help_chunks` with its verified source URL. The `diagnose_symptom` tool cites these real URLs instead of hardcoded ones.
- **KnowledgeService** — Single interface used by all 5 tools. Replaces the old query-time scraper + cache pattern.

### User Experience
- **PartSelect branding** — UI uses PartSelect's blue (#003DA5) color scheme, logo treatment, and typography.
- **Split panel layout** — Chat on the left, contextual detail panel on the right. The panel renders product cards, compatibility results, installation guides, troubleshooting flows, or search results based on `response_type`.
- **Contextual suggested actions** — Backend returns suggested next steps (e.g., "Check compatibility", "How to install this part") as clickable chips.
- **Source citations** — Every product response includes a link back to the PartSelect page.

### Scalability
- **Stateless request handling** — Each API call carries a `session_id`; the backend is horizontally scalable.
- **Session store abstraction** — `SessionStore` ABC with in-memory implementation; swap to Redis without changing the orchestrator.
- **Session windowing** — Conversation history capped at 20 messages to bound token usage per request.

## Features

| Capability | Tool | Detail Panel |
|---|---|---|
| Part search | `search_parts` | Search results list |
| Part details | `get_part_details` | Product card with price, stock, description |
| Compatibility check | `check_compatibility` | Green/red compatibility indicator |
| Installation guide | `get_installation_guide` | Step-by-step instructions |
| Troubleshooting | `diagnose_symptom` | Causes ranked by likelihood |

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
  index/
    schema.sql             # SQLite schema for structured truth store
    structured_store.py    # CRUD + query layer over SQLite
    help_vector_store.py   # FTS-backed semantic help retrieval
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

This crawls up to 50 parts per category (dishwasher + refrigerator) and all available repair guide pages into `partselect_index.db`. Takes ~10–15 minutes. Re-run any time to refresh data.

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
4. **Installation**: "How do I install a dishwasher heating element?"
5. **Part search**: "Find me a dishwasher spray arm"
6. **Scope guardrail**: "What's the weather?" → polite refusal
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

- **Add a new tool**: Decorate a function with `@registry.register()` in `backend/tools/` — schemas auto-generate for OpenAI and Anthropic
- **Add an LLM provider**: Implement `LLMProvider` ABC in `backend/providers/`
- **Add an appliance type**: Extend keyword sets in `preprocessor.py` and symptom entries in `symptom.py`
- **Persistent sessions**: Implement `SessionStore` ABC with a database backend
- **Expand the index**: Run `crawl_partselect.py` with a higher `--limit` or add new category URLs to `CATEGORY_URLS`
