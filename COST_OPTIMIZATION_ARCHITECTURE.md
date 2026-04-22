# COST OPTIMIZATION ARCHITECTURE DIAGRAM

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                                         │
│                     "Write Python code..."                                   │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PHASE 1: PREDICT & COMPARE (Optional)                      │
│                                                                               │
│  User/App can check costs BEFORE making request:                            │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │ POST /api/cost/compare                                       │            │
│  │ {                                                            │            │
│  │   "prompt": "Write Python code...",                         │            │
│  │   "models": ["gemini-2.5-flash", "gpt-4o", "claude-3"]    │            │
│  │ }                                                            │            │
│  │                                                              │            │
│  │ RESPONSE:                                                    │            │
│  │ [                                                            │            │
│  │   {"model": "deepseek", "cost": $0.000086},   ← Cheapest   │            │
│  │   {"model": "gemini", "cost": $0.000091},                  │            │
│  │   {"model": "gpt-4o", "cost": $0.004585},                  │            │
│  │   {"model": "claude", "cost": $0.022755}      ← Most expensive
│  │ ]                                                            │            │
│  └─────────────────────────────────────────────────────────────┘            │
│                                                                               │
│  Save: User chooses deepseek, saves $0.022669 vs claude!                   │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PHASE 2: MAKE REQUEST                                      │
│                                                                               │
│  POST /ask                                                                   │
│  {                                                                            │
│    "user_id": "user123",                                                     │
│    "prompt": "Write Python code...",                                         │
│    "user_tier": 1                                                            │
│  }                                                                            │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE 3: ROUTER SELECTS BEST MODEL                             │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │ Option A: Simple Selection (Top 1 by score)              │               │
│  │  → Just pick the best model                             │               │
│  └──────────────────────────────────────────────────────────┘               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │ Option B: Cost-Optimized Selection (with weights)        │               │
│  │                                                            │               │
│  │ find_optimal_model(                                      │               │
│  │   prompt="Write Python code...",                         │               │
│  │   candidates=[filtered_models],                          │               │
│  │   weight_cost=0.6,      ← 60% priority on cost         │               │
│  │   weight_latency=0.2,   ← 20% priority on speed        │               │
│  │   weight_reward=0.2     ← 20% priority on quality      │               │
│  │ )                                                         │               │
│  │                                                            │               │
│  │ ┌──────────────────────────────────────────────────────┐ │               │
│  │ │ Scores each model:                                   │ │               │
│  │ │ • gemini-2.5-flash:  (0.9 × 0.6) + (0.95 × 0.2) + (0.86 × 0.2) = 0.912 │
│  │ │ • gpt-4o:           (0.7 × 0.6) + (0.8 × 0.2) + (0.91 × 0.2) = 0.762 │
│  │ │ • deepseek:         (0.95 × 0.6) + (0.5 × 0.2) + (0.73 × 0.2) = 0.796 │
│  │ │                                                      │ │               │
│  │ │ Winner: gemini-2.5-flash (score 0.912) ← Best balance! │               │
│  │ └──────────────────────────────────────────────────────┘ │               │
│  └──────────────────────────────────────────────────────────┘               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │ Option C: Multiple Scenario Testing                      │               │
│  │                                                            │               │
│  │ Scenario 1 (Cost-Sensitive):  weight_cost=0.7           │               │
│  │ → Winner: deepseek (cheapest)                           │               │
│  │                                                            │               │
│  │ Scenario 2 (Quality-First): weight_reward=0.8            │               │
│  │ → Winner: claude-3-opus (best quality)                  │               │
│  │                                                            │               │
│  │ Scenario 3 (Balanced): equal weights                      │               │
│  │ → Winner: gpt-4o (best overall value)                   │               │
│  └──────────────────────────────────────────────────────────┘               │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PHASE 4: EXECUTE & MEASURE                                │
│                                                                               │
│  1. Send prompt to selected model                                            │
│  2. Measure response metrics:                                                │
│     - Input tokens: 120                                                      │
│     - Output tokens: 450                                                     │
│     - Latency: 2.3 seconds                                                   │
│     - Response: "def sort(arr)..."                                           │
│                                                                               │
│  3. Calculate EXACT cost:                                                    │
│     - Input cost  = (120 / 1M) × $5.0 = $0.0006                            │
│     - Output cost = (450 / 1M) × $15.0 = $0.00675                          │
│     - Total cost  = $0.00735  ← EXACT for this request!                    │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PHASE 5: TRACK PERFORMANCE                                │
│                                                                               │
│  Update database with metrics:                                               │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐               │
│  │ ModelPerformance Table                                   │               │
│  ├──────────────────────────────────────────────────────────┤               │
│  │ model_id          │ avg_cost   │ avg_latency │ avg_reward│               │
│  ├──────────────────────────────────────────────────────────┤               │
│  │ gemini-2.5-flash  │ $0.000050  │ 1.20s       │ 0.86     │               │
│  │ gpt-4o            │ $0.000150  │ 2.40s       │ 0.91     │               │
│  │ claude-3-opus     │ $0.000250  │ 3.20s       │ 0.95     │               │
│  │ deepseek-chat     │ $0.000010  │ 4.50s       │ 0.73     │               │
│  └──────────────────────────────────────────────────────────┘               │
│                                                                               │
│  These metrics feed back into:                                               │
│  - Thompson Sampling (model selection)                                       │
│  - Cost predictions (future requests)                                        │
│  - A/B test results (model comparison)                                       │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PHASE 6: RESPOND TO USER                                  │
│                                                                               │
│  {                                                                            │
│    "status": "Success",                                                      │
│    "model_used": "gemini-2.5-flash",                                         │
│    "response": "def sort(arr): return sorted(arr)",                          │
│    "metrics": {                                                              │
│      "cost": "$0.00735",                                                     │
│      "latency": 2.3,                                                         │
│      "quality": 0.95,                                                        │
│      "efficiency": 129.3  ← reward per dollar                               │
│    }                                                                          │
│  }                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Cost Calculation Flow

```
INPUT: User Prompt + Model ID
       │
       ├─ Estimate input tokens: len(prompt) / 4 ≈ 120 tokens
       │
       ├─ Execute model
       │  └─ Get output: "def sort(arr)..."
       │
       ├─ Actual output tokens: 450
       │
       ▼
┌────────────────────────────────────┐
│ LOOKUP PRICING FOR MODEL           │
│ (from PROVIDER_PRICING dict)       │
├────────────────────────────────────┤
│ gemini-2.5-flash:                  │
│  input_rate  = $0.075 per 1M       │
│  output_rate = $0.30 per 1M        │
└────────────────────────────────────┘
       │
       ├─ Input cost  = (120 / 1,000,000) × $0.075 = $0.000009
       ├─ Output cost = (450 / 1,000,000) × $0.30 = $0.000135
       │
       ▼
    TOTAL COST = $0.000144 ← EXACT for THIS request!
```

---

## 🔄 A/B Testing Flow

```
COMPARE: Model A vs Model B
         │
         ├─ Fetch historical performance from database
         │
         ├─ Model A Stats:
         │  • avg_cost: $0.00005
         │  • avg_latency: 1.2s
         │  • avg_reward: 0.86
         │
         ├─ Model B Stats:
         │  • avg_cost: $0.00015
         │  • avg_latency: 2.4s
         │  • avg_reward: 0.91
         │
         ├─ SELECT METRIC:
         │  ┌─────────────────────────────────────┐
         │  │ Metric: "cost"                      │
         │  │ Model A wins: $0.00005 < $0.00015  │
         │  │ Improvement: 66.67%                │
         │  └─────────────────────────────────────┘
         │
         │  ┌─────────────────────────────────────┐
         │  │ Metric: "latency"                   │
         │  │ Model A wins: 1.2s < 2.4s           │
         │  │ Improvement: 50.00%                │
         │  └─────────────────────────────────────┘
         │
         │  ┌─────────────────────────────────────┐
         │  │ Metric: "reward"                    │
         │  │ Model B wins: 0.91 > 0.86           │
         │  │ Improvement: 5.81%                 │
         │  └─────────────────────────────────────┘
         │
         │  ┌─────────────────────────────────────┐
         │  │ Metric: "combined" (reward/$)       │
         │  │ A efficiency: 0.86 / $0.00005 = 17200  │
         │  │ B efficiency: 0.91 / $0.00015 = 6067   │
         │  │ Model A wins: 17200 > 6067         │
         │  │ Improvement: 183.6%                │
         │  └─────────────────────────────────────┘
         │
         ▼
      RESULT: Winner + Improvement %
```

---

## 💡 Use Cases

```
┌─────────────────────────────────────────┐
│ USE CASE 1: Cost Optimization           │
│ "Find cheapest model for this task"     │
├─────────────────────────────────────────┤
│ Function: compare_model_costs()         │
│ Input: prompt, [models], expected_tokens│
│ Output: Ranked list (cheapest first)    │
│ Savings: 50-99% cost reduction possible │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ USE CASE 2: Real-Time Performance       │
│ "Get fastest models for low latency"    │
├─────────────────────────────────────────┤
│ Function: get_fastest_models()          │
│ Input: category, limit                  │
│ Output: Models ranked by speed          │
│ Benefit: Sub-2s responses possible      │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ USE CASE 3: Quality Assessment          │
│ "Compare models on quality metrics"     │
├─────────────────────────────────────────┤
│ Function: run_multi_ab_tests()          │
│ Input: [models], category, metric       │
│ Output: All pairwise comparisons        │
│ Benefit: Data-driven model selection    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ USE CASE 4: Value Analysis              │
│ "Get best bang for buck"                │
├─────────────────────────────────────────┤
│ Function: get_cost_efficient_models()   │
│ Input: category, limit                  │
│ Output: Ranked by reward/$              │
│ Benefit: Maximum quality per dollar     │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ USE CASE 5: Smart Selection             │
│ "Balance multiple criteria"             │
├─────────────────────────────────────────┤
│ Function: find_optimal_model()          │
│ Input: candidates, weights              │
│ Output: Best model per scenario         │
│ Benefit: Scenario-based optimization    │
└─────────────────────────────────────────┘
```

---

## 📈 Savings Projection

```
MODEL SELECTION WITHOUT OPTIMIZATION:
Request 1: Random pick → gpt-4o      → $0.017 per request
Request 2: Random pick → claude      → $0.039 per request
Request 3: Random pick → deepseek    → $0.000158 per request
Request 4: Random pick → gpt-4o      → $0.017 per request
       ...
Average: ~$0.018 per request × 100 = $1.80

MODEL SELECTION WITH OPTIMIZATION:
Always choose deepseek (or gemini for quality):
Request 1: Optimized → deepseek      → $0.000158 per request
Request 2: Optimized → deepseek      → $0.000158 per request
Request 3: Optimized → deepseek      → $0.000158 per request
Request 4: Optimized → deepseek      → $0.000158 per request
       ...
Average: $0.000158 per request × 100 = $0.0158

┌──────────────────────────────────────────┐
│ TOTAL SAVINGS: $1.80 - $0.0158 = $1.7842 │
│ PERCENTAGE SAVINGS: 99.1%                │
│                                          │
│ For 10,000 requests: $17,842 saved! 💰   │
└──────────────────────────────────────────┘
```

---

## 🎯 Decision Tree

```
                        USER REQUEST
                             │
                             ▼
                   ┌─────────────────┐
                   │ Get candidate   │
                   │ models (filtered│
                   │ by tier/category│
                   └─────────────────┘
                             │
                             ▼
                   ┌─────────────────────────┐
                   │ Has performance data?   │
                   └─────────────────────────┘
                         /         \
                       YES          NO
                       │             │
                       ▼             ▼
              ┌──────────────┐  ┌─────────┐
              │Use ML        │  │Random   │
              │(A/B tests)   │  │select   │
              └──────────────┘  └─────────┘
                       │             │
                       └─────┬───────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │ Apply weights:           │
                │ cost × 0.3 +             │
                │ latency × 0.2 +          │
                │ reward × 0.5             │
                └──────────────────────────┘
                             │
                             ▼
                ┌──────────────────────────┐
                │ Select best model        │
                │ (highest weighted score) │
                └──────────────────────────┘
                             │
                             ▼
                        EXECUTE
```

---

**Generated:** April 20, 2026
**System:** Cost Optimization & A/B Testing v1.0
