# Router Flow Explanation

---

## Overview

This document describes the complete execution flow of the **TokenShield AI Router** backend, from the moment a client sends a request to the moment the response is returned. It also lists every feature (big and small) that participates in the pipeline.

---

```mermaid
flowchart TD
    %% INPUT
    A[Client POST /ask] --> B[Rate‑limit check]
    B -->|allowed| C[Guardrails (Safety & PII)]
    C -->|passed| D[Semantic Vault lookup]
    D -->|cache hit| E[Return cached response]
    D -->|cache miss| F[Build context]
    F --> G[Conversation history (DB)]
    F --> H[User memory (MemoryService)]
    G & H --> I[Enriched prompt = memory + history + user prompt]

    %% ROUTING
    I --> J[Router → best provider + model + fallbacks]
    J --> K[Prompt compressor (only user prompt)]

    %% EXECUTION
    K --> L[Dispatcher (model execution) – may use images]
    L --> M[Response + token usage]
    L --> N[Circuit‑breaker records success/failure]

    %% POST‑PROCESS
    M --> O[Store in Vault (PostgreSQL + pgvector)]
    O --> P[Learning & reward (Thompson sampler, reward calc)]
    O --> Q[Memory extraction → MemoryService]
    O --> R[Optional feedback endpoint]

    %% OUTPUT
    M --> S[Streaming / JSON response to client]
    S --> T[Client displays result]

    %% FALLBACK LOOP
    N -->|failure| J
```

---

## Detailed Feature List (in execution order)

| Phase | Feature | File(s) | Description |
|------|---------|----------|-------------|
| **0 – Startup** | Rate limiting | `app/main.py` (`_check_rate_limit`) | Limits each user to 30 requests per minute; returns **429** if exceeded. |
| **1 – Safety** | Guardrails / Guardian | `app/guardrails.py` (`GuardrailsChecker.check`) | Scans prompts for jailbreak, prompt‑injection, and PII using `ProtectAI/deberta‑v3‑base‑prompt‑injection‑v2`. Blocks malicious prompts (400) and redacts PII. |
| **2 – Cache** | Semantic Vault (vector cache) | `app/vault_service.py` (`semantic_search`) | Performs L2 vector similarity (< 0.55) and keyword‑overlap (≥ 0.75) checks against prior conversations; returns verified cache hits. |
| **3 – Context building** | Conversation history | `app/main.py` | Retrieves last *N* turns (default 5) from `UserConversation` and formats as `[CONVERSATION HISTORY]`. |
| | Persistent user memory | `app/memory_service.py` (`MemoryService.get_memories`) | Stores long‑term facts (e.g., "prefers Python"); injected into prompt via `build_memory_context`. |
| | Prompt compression | `app/routing/prompt_compressor.py` (`compress`) | Reduces only the **new user message** (removes stop‑words, repeats); reports percentage saved. |
| **4 – Routing** | Intelligent model selection | `app/vault_service.py` (`get_best_provider_and_model`) → `router.get_best_model` | Chooses cheapest model satisfying tier & complexity; returns primary + same‑category fallbacks. |
| | Fallback cascade | `app/main.py` (loop over `models_to_try`) | Primary → same‑category → cross‑category → safety‑fallback list. |
| | Circuit breaker | `app/routing/circuit_breaker.py` | Skips models that have failed > 3 times in the last 5 min; auto‑reopens after cooldown. |
| **5 – Execution** | Dispatcher | `core/dispatcher.py` (`Dispatcher.execute`) | Sends compressed prompt to the selected provider; supports optional `image_base64`/`image_url` for multi‑modal calls. |
| **6 – Persistence** | Vault storage | `app/vault_service.py` (`save_to_vault`) | Saves the interaction (prompt, response, token count, cost, embedding) into `UserConversation` with optional `session_id`. |
| | Conversation archiving (optional) | `app/vault_service.py` (`_archive_session`) | Summarizes old conversation via a tiny LLM call and stores in `ConversationArchive`. |
| **7 – Learning & Reward** | Reward calculation | `app/vault_service.py` (`calculate_and_update_reward`) | Computes quality score (code detection, error words) → reward → updates Thompson sampler & DB model performance. |
| | Thompson sampling bandit | `app/routing/thompson_sampler.py` (`update_bandit_reward`) | Maintains per‑model Beta distribution; higher‑reward models are preferred over time. |
| | Adaptive prompt compressor | `app/routing/prompt_compressor.py` (`learn_from_feedback`) | Adjusts compression aggressiveness based on received reward. |
| **8 – Feedback endpoint** | User feedback | `app/main.py` (`/feedback`) | Accepts thumbs‑up/down + optional comments; converts to reward (0‑1) and feeds bandit. |
| **9 – Monitoring** | System event logging | `app/vault_service.py` (`log_system_event`) | Inserts rows into `SystemLog` for events such as cache‑hit, guardrails‑blocked, fallback‑used. |
| **10 – Health & Diagnostics** | Health check | `app/main.py` (`/health`) | Returns JSON with enabled features, mode, Redis status. |
| **11 – Miscellaneous** | API‑key tester | `app/main.py` (`/test-key`) | Sends a minimal request to a provider to verify API‑key validity. |
| | Streaming SSE endpoint | `app/main.py` (`/ask/stream`) | Sends tokens to client as they are generated; also supports cache‑hit streaming. |
| | Multi‑modal support | `app/main.py` & `dispatcher` | Accepts `image_base64` or `image_url` for vision models. |
| | Safe‑fallback model list | `config/settings.py` (`SAFE_FALLBACK_MODELS`) | Guarantees that a response is always produced even if all other models fail. |
| | Non‑text keyword filter | `router.get_best_model` | Skips models whose IDs contain keywords like `image`, `audio`, etc., for pure‑text queries. |
| | Redis placeholders (currently disabled) | Various files | Commented‑out Redis caching logic for future activation. |
| | Environment loading | `app/main.py` (`load_dotenv()`) | Loads `.env` early so all modules can read configuration. |
| | Cost calculation fallback rates | `app/vault_service.py` (`_calculate_cost`) | Uses DB rates if present; otherwise uses hard‑coded defaults per provider. |
| | Robust exception handling | Throughout | Wraps DB/LLM calls in `try/except` with clear logging to avoid crashes. |

---

### How to read the diagram
- **Blue boxes** – external inputs/outputs (client, DB). 
- **Green boxes** – core processing stages. 
- **Orange arrows** – normal successful flow. 
- **Red arrows** – failure paths that trigger fall‑backs.

---

*This file is intended for developers and reviewers who need a single‑source description of the router’s behaviour.*
