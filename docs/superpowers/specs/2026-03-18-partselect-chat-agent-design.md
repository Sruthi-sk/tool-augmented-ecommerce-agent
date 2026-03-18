# PartSelect Chat Agent — Design Spec

## Context

Instalily case study: build a chat agent for the PartSelect e-commerce website focused on Refrigerator and Dishwasher parts. The agent provides product information and assists with customer transactions. It must stay strictly within scope — no general-purpose chatbot behavior.

The evaluation criteria: interface design, agentic architecture, extensibility/scalability, and accurate query resolution. A video walkthrough and slide deck will accompany the code.

**Note:** The provided CRA template (`case-study-main/`) is a reference scaffold only. We are building a fresh Next.js project as the instructions recommend a modern framework. The template's chat UI patterns (message bubbles, input handling) inform our design but we are not building on top of CRA.

## Architecture

Two-service architecture:
- **Next.js frontend** (TypeScript) — split-panel chat UI with PartSelect branding
- **FastAPI backend** (Python) — tool endpoints, retrieval, caching, LLM agent layer

### Data Flow

```
User message + session state
    ↓
Pre-processor (deterministic: regex + keyword scope check, entity extraction, slot detection)
    ↓
[Out of scope?] → Polite refusal (no LLM call, saves tokens)
[Missing required slot?] → Follow-up question (e.g., "What's your model number?")
    ↓
LLM Provider Adapter (Anthropic/OpenAI) → provider-native tool calling
    ↓
Tool execution → PartSelect retrieval + cache → structured result
    ↓
Update session state
    ↓
LLM composes response from tool result + session context (this step is streamed to frontend)
    ↓
Frontend renders rich UI cards + source citations
```

### Streaming Architecture

Tool_use requires a multi-step flow, not a simple stream-through:

1. **First LLM call** (not streamed to user): send user message + tools → Claude returns tool_use block
2. **Tool execution**: run the selected tool, get structured result
3. **Second LLM call** (streamed to user): send tool result → Claude composes natural language response

The frontend shows a loading/thinking indicator during steps 1-2, then streams step 3 via SSE. If we hit time constraints, we fall back to request-response with a loading spinner — still good UX.

## Frontend (Next.js + TypeScript)

### Layout: Split Panel
- **Left: Chat Panel** — message list, typing indicator, input bar, quick suggestion chips
- **Right: Detail Panel** — renders contextual content based on last tool result

### Components
- `ChatPanel` — message bubbles (user/assistant), markdown support, auto-scroll, streaming text
- `DetailPanel` — switches view based on `response_type` field in the API response:
  - `"product"` → `ProductCard` — part name, image placeholder, price, stock status, compatibility badge, PartSelect link
  - `"compatibility"` → `CompatibilityResult` — green/red indicator, model info, compatible parts list
  - `"installation"` → `InstallationGuide` — numbered steps, difficulty rating, tools needed
  - `"troubleshooting"` → `TroubleshootingFlow` — symptom description, possible causes, recommended replacement parts
  - `"search_results"` → `SearchResults` — list of matching parts as clickable cards
  - `null` → welcome/empty state with usage examples
- `QuickSuggestions` — contextual chips driven by `suggested_actions` field from backend response (e.g., after showing a part: "Check compatibility", "How to install", "View on PartSelect")
- `MessageBubble` — individual message with source citation link if applicable

### Branding
- PartSelect blue (#003DA5) as primary color
- Clean, professional typography
- PartSelect logo in header
- Consistent with the e-commerce feel of the actual site

### API Integration
- Single endpoint: `POST /api/chat` (Next.js API route proxies to FastAPI)
- Streaming via SSE for the response composition step
- Session ID managed via header (`X-Session-ID`, generated client-side with UUID)

## Backend (FastAPI + Python)

### Environment Setup
- Python 3.11+
- Required env vars: `OPENAI_API_KEY` (default provider), optional `ANTHROPIC_API_KEY`
- Install: `pip install -r requirements.txt`
- Run: `uvicorn main:app --reload --port 8000`
- CORS: allow `http://localhost:3000` (Next.js dev server)

### Directory Structure
```
backend/
├── main.py                 # FastAPI app, CORS, routes
├── config.py               # Environment config, provider selection
├── providers/
│   ├── base.py             # LLMProvider ABC
│   ├── openai_provider.py  # OpenAI implementation (DEFAULT) — uses `openai` Python SDK
│   └── claude_provider.py  # Claude implementation — uses `anthropic` Python SDK
├── agent/
│   ├── orchestrator.py     # Main agent loop: preprocess → LLM → tools → respond
│   ├── preprocessor.py     # Deterministic scope check, entity extraction, slot detection
│   └── session.py          # Session state class with clean read/update interface
├── tools/
│   ├── registry.py         # Tool registration + schemas for LLM
│   ├── search.py           # search_parts(query, appliance_type)
│   ├── part_details.py     # get_part_details(part_number)
│   ├── compatibility.py    # check_compatibility(part_number, model_number)
│   ├── installation.py     # get_installation_guide(part_number)
│   └── symptom.py          # diagnose_symptom(appliance_type, symptom, model?)
├── retrieval/
│   ├── scraper.py          # PartSelect HTML fetching + BeautifulSoup parsing
│   └── cache.py            # SQLite cache layer with TTL
├── seed/
│   └── seed_data.json      # ~10 pre-scraped popular parts (PRIMARY data source for demo)
└── tests/
```

### API Contract

**Request:** `POST /api/chat`
```json
{
  "message": "Is part PS11752778 compatible with my WDT780SAEM1?",
  "session_id": "uuid-string"
}
```

**Response (SSE stream):**
```
data: {"type": "status", "content": "Checking compatibility..."}
data: {"type": "text", "content": "Yes, part PS11752778 is compatible..."}
data: {"type": "text", "content": " with your WDT780SAEM1 model."}
data: {"type": "detail", "response_type": "compatibility", "data": {"compatible": true, "part_number": "PS11752778", "model_number": "WDT780SAEM1", "part_name": "Water Inlet Valve", "source_url": "https://www.partselect.com/..."}}
data: {"type": "suggested_actions", "actions": ["How to install this part", "View on PartSelect", "Find similar parts"]}
data: {"type": "done"}
```

**Non-streaming fallback:**
```json
{
  "message": "Yes, part PS11752778 is compatible...",
  "response_type": "compatibility",
  "detail_data": { ... },
  "source_url": "https://www.partselect.com/...",
  "suggested_actions": ["How to install this part", "View on PartSelect"]
}
```

### LLM Provider Abstraction

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages, system, tools) -> LLMResponse: ...

    @abstractmethod
    async def stream(self, messages, system, tools) -> AsyncIterator[LLMChunk]: ...

class OpenAIProvider(LLMProvider):
    # Uses `openai` Python SDK, function calling format (DEFAULT provider)

class ClaudeProvider(LLMProvider):
    # Uses `anthropic` Python SDK, Claude tool_use format
```

Config selects the provider (default: OpenAI). All agent code calls `provider.generate()` — never a specific SDK directly. Both providers are fully implemented.

### Session State

Session is a proper class, not a raw dict. Single file (`session.py`) owns all state logic.

```python
class Session:
    session_id: str
    appliance_type: Optional[str]      # "refrigerator" | "dishwasher"
    model_number: Optional[str]
    part_number: Optional[str]
    brand: Optional[str]
    symptom: Optional[str]
    last_tool_result: Optional[dict]
    last_source_url: Optional[str]
    conversation_history: list[Message]  # windowed: keep last 20 messages

    def update(self, **kwargs) -> None: ...
    def get_context_for_llm(self) -> dict: ...
    def clear_slot(self, slot: str) -> None: ...

class SessionStore(ABC):
    async def get(self, session_id: str) -> Session: ...
    async def save(self, session: Session) -> None: ...

class InMemorySessionStore(SessionStore): ...
# Future: class SQLiteSessionStore(SessionStore): ...
```

Clean interface. In-memory now, SQLite-persistable later via the abstract `SessionStore`. Conversation history is windowed to the last 20 messages to avoid exceeding context limits.

### System Prompt

```
You are the PartSelect Parts Assistant, helping customers find and learn about
refrigerator and dishwasher replacement parts.

RULES:
- ONLY answer questions about refrigerator and dishwasher parts from PartSelect.
- NEVER invent or guess product information. Only use data returned by your tools.
- ALWAYS cite the source URL when providing factual product information.
- If a tool returns no results, say so honestly — do not fabricate an answer.
- If you need a model number or part number to help, ask for it.
- Do not answer questions about other appliances, general knowledge, or unrelated topics.
  Politely redirect: "I can only help with refrigerator and dishwasher parts from PartSelect."

AVAILABLE TOOLS:
[tool schemas injected here by the orchestrator]

RESPONSE FORMAT:
- Be concise and helpful
- Lead with the direct answer
- Include the source link
- Suggest logical next steps (e.g., "Would you like installation instructions?")

CONVERSATION CONTEXT:
[session state injected here: known model, appliance type, recent part context]
```

### Pre-processor

Fully deterministic — no LLM call. Saves tokens and latency.

1. **Scope check** — keyword/regex matching against appliance terms, part-related vocabulary. Allowlist approach: if the message contains refrigerator/dishwasher/parts-related terms OR references a known model/part number format, it's in-scope. Otherwise, reject.
2. **Entity extraction** — regex patterns for:
   - Model numbers (e.g., WDT780SAEM1, WRF535SWHZ — brand-specific patterns)
   - Part numbers (PS prefix + digits, or PartSelect URL patterns)
   - Brand names (Whirlpool, GE, Samsung, LG, Maytag, etc.)
   - Symptom keywords (not working, leaking, noisy, won't start, etc.)
3. **Slot detection** — based on detected intent: compatibility needs part# + model#, installation needs part#, etc.
4. **Session update** — store any newly extracted entities in session

### Tools

Each tool:
1. Has a schema (name, description, parameters) registered in `registry.py`
2. Calls the retrieval layer for PartSelect data
3. Returns structured JSON (not free text)
4. Includes `source_url` for citation

**Tool definitions:**

| Tool | Parameters | Returns |
|------|-----------|---------|
| `search_parts` | query, appliance_type | List of matching parts with basic info |
| `get_part_details` | part_number | Full part details (price, stock, description, compatible models) |
| `check_compatibility` | part_number, model_number | Boolean + details, alternative parts if incompatible |
| `get_installation_guide` | part_number | Step-by-step instructions, difficulty, tools needed |
| `diagnose_symptom` | appliance_type, symptom, model_number? | Possible causes, recommended replacement parts |

**`diagnose_symptom` data source:** Scrapes PartSelect's symptom/repair help pages (e.g., `partselect.com/Repair/Refrigerator/Ice-Maker-Not-Working/`). These pages list common causes and recommended replacement parts. Falls back to seed data for common symptoms if scraping fails.

### Retrieval + Cache

```python
class PartSelectRetriever:
    async def fetch_part(self, part_number: str) -> PartData: ...
    async def search(self, query: str, appliance_type: str) -> list[PartSummary]: ...
    async def fetch_model_parts(self, model_number: str) -> list[PartSummary]: ...

class CacheLayer:
    # SQLite-backed
    async def get(self, key: str) -> Optional[CachedItem]: ...
    async def set(self, key: str, data: dict, ttl_hours: int = 24): ...
    async def get_or_fetch(self, key: str, fetcher: Callable) -> dict: ...
```

- **Seed data is the primary source for demos** — ~10 pre-scraped popular parts ensure reliable demo behavior
- Live retrieval is best-effort enhancement for parts not in seed data
- Cache-first: check SQLite before hitting PartSelect
- TTL-based expiry (24h default)
- HTML parsing with BeautifulSoup extracts structured fields from PartSelect pages

### Error Handling

| Scenario | Behavior |
|----------|----------|
| PartSelect unreachable | Return seed data if available, otherwise: "I'm having trouble looking that up right now. Please try again or visit partselect.com directly." |
| HTML parsing fails | Log error, return partial data if possible, otherwise graceful fallback message |
| LLM returns malformed tool call | Log + retry once with a clarified prompt. If still fails, return: "I had trouble processing that. Could you rephrase?" |
| Session not found | Create new session with provided session_id |
| Rate limiting from PartSelect | Exponential backoff, fall back to cached/seed data |

### Guardrails

1. **Pre-processor scope check** — deterministic rejection before LLM call (saves tokens)
2. **System prompt constraints** — Claude instructed to only use provided tools, never invent product data
3. **Tool result validation** — if tool returns no data, respond honestly ("I couldn't find that part")
4. **No speculation** — never guess compatibility without source evidence
5. **Citation required** — every factual answer includes source URL

## Agent Behavior

The agent:
- Classifies query into supported intent via deterministic pre-processor
- Calls the right backend tool via LLM tool_use
- Answers only from tool results
- Cites the source page used
- Asks narrow follow-ups only when required fields are missing
- Refuses anything outside refrigerator/dishwasher parts scope
- Does not guess compatibility without evidence

## Non-Goals

- General web chatbot / knowledge base
- Appliance categories beyond refrigerator and dishwasher
- Legal, medical, or general knowledge questions
- Speculative compatibility answers
- User authentication or real order management
- Payment processing

## Verification

1. **Frontend**: `npm run dev` — chat UI loads, split panel renders, PartSelect branding visible
2. **Backend**: `uvicorn main:app` — API starts, `/docs` shows Swagger with all endpoints
3. **End-to-end tests** (manual):
   - "Is part PS11752778 compatible with WDT780SAEM1?" → compatibility check with source citation
   - "My Whirlpool fridge ice maker isn't working" → symptom diagnosis + recommended parts
   - "How do I install PS11752778?" → installation guide with steps
   - "What's the weather today?" → polite refusal (out of scope)
   - "Find me a dishwasher spray arm" → part search results with product cards
4. **Streaming**: responses appear incrementally during composition step; loading indicator during tool execution
5. **Session continuity**: "Is it compatible with my model?" (after providing model earlier) → uses session state
6. **Error resilience**: disconnect backend → frontend shows graceful error; unknown part → honest "not found" response
