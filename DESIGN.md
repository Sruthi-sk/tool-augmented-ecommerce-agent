# Design Document — PartSelect Chat Agent

## Overview

This agent is built to assist PartSelect customers with one specific job: **finding the right replacement part and getting it installed**. Every design decision is evaluated against that function. The agent does not aim to be a general-purpose assistant — that would compromise the precision needed for e-commerce parts work.

The implementation is a two-service system: a **Next.js frontend** (TypeScript) and a **FastAPI backend** (Python). The frontend provides the chat interface and rich product UI. The backend handles all agent logic, data retrieval, and LLM orchestration.

---

## Interface Design

### Split Panel Layout

The UI uses a persistent split panel: chat on the left, context on the right. This is a deliberate departure from a full-screen chat layout.

The core insight is that appliance parts are **visual, technical products**. A user asking "is PS11752778 compatible with my dishwasher?" needs to see a clear compatible/incompatible indicator, the model number confirmed, and a link to buy — not just read a paragraph. Forcing all of that into a chat bubble creates a poor information hierarchy.

The right panel renders different component types based on `response_type` returned by the backend:

| `response_type` | Component | What the user sees |
|---|---|---|
| `product` | `ProductCard` | Part name, price, stock status, description, PartSelect link |
| `compatibility` | `CompatibilityResult` | Green/red indicator, confirmed part + model, source link |
| `installation` | `InstallationGuide` | Numbered steps, difficulty rating |
| `troubleshooting` | `TroubleshootingFlow` | Symptom summary, likely causes ranked by likelihood, recommended parts |
| `search_results` | `SearchResults` | Clickable part cards with basic info |

The chat panel carries the conversation. The detail panel carries the facts. They serve different purposes and shouldn't compete for the same space.

### Suggested Actions

After every response, the backend returns a `suggested_actions` list — context-aware chips displayed below the last message. These are not generic ("ask me anything") — they're derived from what just happened:

- After a product detail: "Check compatibility", "How to install this part", "View on PartSelect"
- After a compatibility check (compatible): "How to install this part", "View part details"
- After a compatibility check (incompatible): "Find compatible parts", "Search for alternatives"
- After troubleshooting: "Find replacement parts", "Check compatibility"

This guides users through a natural transaction flow — from symptom → diagnosis → part selection → compatibility check → installation — without requiring them to know what to ask next.

### Branding

The UI matches PartSelect's visual identity: primary blue `#003DA5`, clean typography, logo in the header. The design intent is to feel like a native feature of the PartSelect site, not a third-party chat widget bolted on.

---

## Agentic Architecture

### Pipeline

Every user message passes through a fixed pipeline:

```
User message
    │
    ▼
Preprocessor (deterministic — no LLM)
    │ out-of-scope? → immediate refusal, no LLM call
    │ entities extracted → session updated
    ▼
LLM Pass 1: tool routing
    │ provider returns a tool_call
    ▼
Tool execution → KnowledgeService → SQLite structured index
    │ structured result returned
    ▼
LLM Pass 2: response composition
    │ LLM writes natural language from tool result
    ▼
Validation / grounding (deterministic)
    │ hallucinated facts rewritten to match detail_data
    ▼
Response → frontend
```

### Deterministic Preprocessor

The preprocessor runs before any LLM call. It does three things:

1. **Scope check** — keyword allowlist covering appliance terms (`refrigerator`, `dishwasher`, `ice maker`, `spray arm`, ...), part vocabulary (`replace`, `compatible`, `install`, `valve`, `gasket`, ...), and known brands. If none match and no part/model number is present in the message or session, the message is rejected with a canned response. No tokens spent.

2. **Entity extraction** — regex patterns for part numbers (`PS\d{6,10}`), model numbers (brand-specific alphanumeric patterns), appliance type, and brand names. Extracted entities are stored in session state for multi-turn use.

3. **Session continuity** — if a session already has an active part number or model number on record, short follow-up messages ("yes", "how do I install it?") pass through even if they don't contain keywords. This prevents scope false-rejections mid-conversation.

**Why deterministic, not LLM-based:** Scope enforcement via LLM is fragile — it can be prompt-injected or confused by borderline phrasing. Regex allowlists are more reliable for this exact domain. Entity extraction via regex is more precise than LLM extraction for structured identifiers like `PS11752778` or `WDT780SAEM1`.

### Two-Pass LLM Flow

The LLM makes two calls per turn, not one:

- **Pass 1 (routing):** The LLM receives the conversation history, session context, and tool schemas. Its only job is to select the right tool and arguments. The user does not see this step — they see a loading indicator.
- **Pass 2 (composition):** The LLM receives the tool result and writes a natural language response. This is what gets sent to the user.

Separating routing from generation means each pass has a single, well-defined objective. A combined single-pass call creates tension between tool selection quality and response prose quality.

The orchestrator supports up to **two tool calls per turn** to cover chained flows (e.g., `search_parts` → `get_part_details`) without requiring a second user message.

### Grounding / Validation Layer

After pass 2, `agent/validation.py` compares the LLM's response against `detail_data` — the raw structured result from the tool. If the response contains a part number, model number, price, or URL that doesn't match the tool output, the validator replaces the affected sentence with a grounded template.

This is a string-comparison check, not another LLM call. For e-commerce facts, the correctness signal is binary: either the part number matches or it doesn't. An LLM judge would add latency and cost to a problem that doesn't require language understanding to detect.

### Provider Abstraction

```python
class LLMProvider(ABC):
    async def generate(self, messages, system, tools) -> LLMResponse: ...

class OpenAIProvider(LLMProvider):   # default, function calling
class ClaudeProvider(LLMProvider):   # Anthropic tool_use format
```

All agent code calls `provider.generate()`. Tool schemas are auto-translated to the correct format per provider by `ToolRegistry.get_schemas(provider)`. Switching providers is one env var: `LLM_PROVIDER=anthropic`.

---

## Accuracy and Efficiency of Query Resolution

### Accuracy

The agent has **three layers of fact correctness**:

1. **Data quality at ingestion** — `ingestion/crawl_partselect.py` uses Crawl4AI (Playwright-backed) to fetch real PartSelect pages in two passes: (a) part detail pages for structured product data (part number, MPN, price, stock status, description, compatible models, symptoms, installation narratives), and (b) repair guide pages (`/Repair/{Appliance}/{Symptom}/`) for troubleshooting content. Both passes store a verified `source_url` in the DB, so every citation in a response traces back to a real PartSelect page.

2. **LLM instructed not to speculate** — the system prompt states: *"NEVER invent or guess product information. Only use data returned by your tools."* The tool results contain all the facts; the LLM's job is composition, not recall.

3. **Post-generation grounding** — the validation layer catches the cases where the LLM doesn't follow instructions. Hallucinated part numbers and prices are overwritten before the response leaves the backend.

### Efficiency

- **Scope rejections cost ~0ms** — out-of-scope queries are rejected by the preprocessor before any LLM call. Common for a parts assistant that will receive off-topic messages in production.
- **No query-time scraping** — the backend queries SQLite, not PartSelect. Average tool execution time is under 10ms. All latency is in the LLM calls.
- **FTS5 for search** — part name and description search uses SQLite's FTS5 full-text index with Porter stemming. Queries like "dishwasher spray arm" match correctly even with inflection variations.
- **Bounded tool calls** — the orchestrator caps at 2 tool calls per turn. This prevents runaway multi-hop reasoning while covering the most useful chained flows.
- **Session windowing** — conversation history is capped at 20 messages. Older context is dropped from the LLM prompt to keep token usage bounded as conversations grow long.

---

## Data Layer

### Why Offline Indexing

PartSelect blocks plain HTTP clients (403). Scraping at query time would require spinning up a Playwright browser per request — adding 5–10 seconds of latency per turn. The offline approach moves that cost to ingestion time, not user time.

The ingestion script (`ingestion/crawl_partselect.py`) runs once to populate `partselect_index.db`. At runtime, all tools query SQLite. The database can be refreshed by re-running the script.

### Schema

```
parts                    — core product facts (part_number, name, price, in_stock, description, mpn, source_url)
models                   — appliance model records (model_number, brand, appliance_type)
part_compatibility       — part ↔ model many-to-many
part_installation_steps  — ordered installation narratives per part
part_symptoms            — symptom tags extracted from user repair stories per part
troubleshooting_causes   — appliance+symptom → likely cause + part type (from built-in KB)
help_chunks              — scraped repair guide content (help_type='repair_guide', symptom_key, source_url, chunk_text)
help_chunks_fts          — FTS5 virtual table over help_chunks (keyword search at troubleshooting time)
parts_fts                — FTS5 virtual table over parts (name + description)
```

`help_chunks` is populated by the repair guide scraping pass in `crawl_partselect.py`. Each row corresponds to one PartSelect repair guide page (e.g. `/Repair/Refrigerator/Not-Making-Ice/`), keyed by a normalized `symptom_key`. When `diagnose_symptom` is called and no structured causes are found in `troubleshooting_causes`, `KnowledgeService` falls back to FTS search over `help_chunks` and returns the matching guide's `source_url` — giving the user a verified, live PartSelect repair URL instead of a hardcoded one.

The structured store (`index/structured_store.py`) and help index (`index/help_vector_store.py`) are accessed only through `KnowledgeService` — a single interface that all tools call. This means the underlying storage can be replaced without touching tool code.

---

## Extensibility and Scalability

### Adding a New Tool

Registering a new capability is a single decorator:

```python
@registry.register(
    name="get_warranty_info",
    description="Look up warranty terms for a part.",
    parameters={
        "type": "object",
        "properties": {"part_number": {"type": "string"}},
        "required": ["part_number"],
    },
)
async def get_warranty_info(part_number: str) -> dict:
    ...
```

The schema auto-generates in both OpenAI (function calling) and Anthropic (tool_use) formats. The orchestrator picks it up automatically. No changes to routing logic, session handling, or the frontend beyond adding a new `response_type` case to `DetailPanel` if a new panel component is needed.

### Adding a New LLM Provider

Implement `LLMProvider(ABC)` in `backend/providers/`, set `LLM_PROVIDER=yourprovider` in `.env`. The rest of the stack is unchanged.

### Extending to New Appliance Categories

The scope check, symptom KB, and ingestion script are the three places to update:

1. Add keywords to `preprocessor.py`
2. Add symptom entries to `tools/symptom.py` (fallback KB for symptoms not yet in the DB)
3. Add the new parts category URL to `CATEGORY_URLS` in `ingestion/crawl_partselect.py`
4. The repair guide scraper auto-discovers guides from `/Repair/{Appliance}/` — add the new appliance's repair index URL to `REPAIR_INDEXES` in `scrape_and_ingest_repair_guides()`

### Session Persistence

`SessionStore` is an ABC:

```python
class SessionStore(ABC):
    async def get(self, session_id: str) -> Session: ...
    async def save(self, session: Session) -> None: ...
```

The current `InMemorySessionStore` is suitable for a single-instance demo. A `RedisSessionStore` or `SQLiteSessionStore` is a drop-in replacement — no changes to the orchestrator, tools, or API layer.

### Horizontal Scaling

Each API request is stateless from the backend's perspective: the `session_id` header carries all state context. With a persistent `SessionStore` (Redis or a database), multiple backend instances can serve the same user session. The SQLite index is read-only at runtime, so it can be shared across instances via a mounted volume or replaced with Postgres using the same `KnowledgeService` interface.

---

## User Experience Decisions

### The agent asks narrow questions, not broad ones

When the user asks about compatibility but hasn't mentioned a model number, the session state check detects the missing slot. Rather than asking "what appliance do you have, what brand is it, and what's the model number?", the agent asks one thing: "What's your model number?" This minimizes friction at the point where users are most likely to abandon.

### Scope refusals are brief and redirect constructively

Out-of-scope responses don't just say "I can't help with that." They say: *"I can only help with refrigerator and dishwasher parts from PartSelect. Could you ask me about finding parts, checking compatibility, installation help, or troubleshooting for these appliances?"* — giving the user a concrete path back into scope.

### Source citations on every factual response

Every tool result includes `source_url`. Every product response includes it in the reply. Users can click through to verify pricing, stock, and purchase — which is the actual transaction goal of the assistant.

### Responses lead with the answer

The system prompt instructs the LLM to lead with the direct answer, not preamble. "Yes, PS11752778 is compatible with your WDT780SAEM1" — not "Great question! Let me check that for you. Based on my research..."

---

## What's Intentionally Out of Scope

| Item | Reason |
|---|---|
| Order placement / cart integration | Requires PartSelect backend API access not available for a case study |
| Auth / user accounts | Out of scope; `session_id` is a client-generated UUID sufficient for stateful conversations |
| Real-time price / stock sync | Offline index is refreshed by re-running ingestion; acceptable for a demo |
| Vector embeddings for semantic search | FTS5 with Porter stemming is sufficient for the dataset size; embeddings add infra cost without material quality improvement at this scale |
| Streaming prose to the frontend | The infrastructure is in place (SSE endpoint, streaming provider methods); the detail panel requires the complete `detail_data` object before rendering, so the user sees a loading indicator during tool execution and then the full response |
