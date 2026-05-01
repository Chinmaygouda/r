# AI Router Pipeline v2.0

A production-grade AI model router with local DeBERTa-v3 classification, semantic vault caching, cascading multi-provider fallbacks, and persistent user memory.

## Features

| Feature | Description |
|---|---|
| **Streaming** | Token-by-token SSE responses via `/ask/stream` |
| **Multi-Turn History** | Conversation context persisted in PostgreSQL, linked by `session_id` |
| **Multi-Modal Vision** | Image input (base64 or URL) via Gemini, Claude, GPT-4o |
| **Guardrails** | Prompt injection detection + PII redaction (email, phone, Aadhaar, PAN) |
| **User Memory** | Persistent per-user facts extracted automatically and prepended to future prompts |
| **Semantic Cache** | `pgvector` PostgreSQL cache using local `bge-base-en-v1.5` embeddings (No Redis required!) |
| **Cost Tracking** | Dynamic price-per-token calculation streamed via `[METRICS]` SSE payload |
| **API Validation** | Secure `/test-key` endpoint to validate provider keys without browser CORS issues |
| **Operator Prompt** | Global system prompt override via `.env` |
| **Cascading Fallback** | Same-category → Cross-category → Last-resort with circuit breaker |
| **Thompson Sampling** | Bandit learns from reward signals to prefer high-performing models |
| **Prompt Compression** | Local compressor reduces token usage 30-50% before calling any AI |

## Quick Start

### 1. Prerequisites

**Python 3.11 or 3.12** is required. (3.14 has Pydantic V1 incompatibility.)

If you are cloning — install Git LFS first (the DeBERTa model weights are ~539 MB):
```bash
git lfs install
git clone <your-repo-url>
git lfs pull
```

### 2. Setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Minimum required keys in `.env`:
```env
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
GEMINI_API_KEY=your-google-ai-studio-key
```

### 4. Run

```bash
uvicorn app.main:app --reload
```

API docs available at: **http://127.0.0.1:8000/docs**

---

## API Endpoints

### `POST /ask` — Main Endpoint
```json
{
  "user_id": "user_123",
  "prompt": "Write a Python FastAPI CRUD app",
  "user_tier": 2,
  "session_id": "my-session-001",
  "max_history_turns": 5,
  "image_url": "https://example.com/image.png"
}
```

### `POST /ask/stream` — Streaming (SSE)
Same body as `/ask`. Returns tokens as Server-Sent Events.

### `GET /memory/{user_id}` — View User Memory
Returns all extracted facts remembered for a user.

### `DELETE /memory/{user_id}` — Clear Memory

### `POST /test-key` — Validate API Keys
```json
{
  "provider": "Google",
  "api_key": "your-key",
  "model_id": "gemini-2.5-flash"
}
```

### `POST /feedback` — Submit Quality Feedback
```json
{
  "vault_id": "42",
  "feedback": 1.0,
  "comments": "Great response"
}
```

### `GET /health` — Health Check

---

## Folder Structure

```
├── app/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── models.py            # SQLAlchemy DB models
│   ├── vault_service.py     # Semantic cache + routing orchestration
│   ├── guardrails.py        # Safety checks + PII redaction
│   ├── memory_service.py    # User memory extraction + retrieval
│   ├── database_init.py     # DB engine, session factory, migrations
│   └── routing/
│       ├── router.py        # Main routing logic (DeBERTa + heuristics)
│       ├── scoring.py       # Model scoring formula
│       ├── confidence.py    # Confidence calculation
│       ├── bandit.py        # Thompson Sampling exploration
│       ├── circuit_breaker.py  # Per-model failure tracking
│       ├── reward.py        # Reward signal computation
│       └── prompt_compressor.py  # Token reduction
├── core/
│   ├── dispatcher.py        # Multi-provider AI execution engine
│   ├── auto_discovery.py    # Librarian: syncs available models from providers
│   └── librarian.py        # Model registry manager
├── config/
│   └── settings.py          # All tunable constants (thresholds, weights, keywords)
├── database/
│   └── db.py                # Model fetch helpers
├── docs/                    # Development notes and architecture docs
├── models/                  # Local ML model weights (DeBERTa, BGE-Base)
├── .env.example             # Environment variable template
└── requirements.txt
```

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (NeonDB, Supabase, etc.) |
| `GEMINI_API_KEY` | ✅ | Primary AI provider + router backbone |
| `ANTHROPIC_API_KEY` | Optional | Claude fallback |
| `OPENAI_API_KEY` | Optional | GPT-4o fallback |
| `OPERATOR_SYSTEM_PROMPT` | Optional | Customizes all AI responses globally |
| `API_SECRET_KEY` | Optional | Bearer token for endpoint security |
