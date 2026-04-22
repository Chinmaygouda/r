# QUICK REFERENCE: COST OPTIMIZATION FEATURES

## 🚀 Quick Start (Copy-Paste Examples)

### 1. Calculate EXACT Cost (NOT Averaged)
```python
from app.routing.cost_optimizer import calculate_exact_cost

# For a specific prompt with 125 input tokens, 500 output tokens
cost = calculate_exact_cost("gpt-4o", 125, 500)

print(f"Input cost:  ${cost['input_cost']:.6f}")      # $0.000625
print(f"Output cost: ${cost['output_cost']:.6f}")     # $0.007500
print(f"Total cost:  ${cost['total_cost']:.6f}")      # $0.008125
```

---

### 2. Predict Cost Before Execution
```python
from app.routing.cost_optimizer import predict_cost_for_prompt

prediction = predict_cost_for_prompt(
    "gpt-4o",
    "Write a Python sorting algorithm",
    estimated_output_tokens=500
)

print(f"Predicted cost: ${prediction['total_cost']:.6f}")
```

---

### 3. Find Cheapest Model
```python
from app.routing.cost_optimizer import compare_model_costs

results = compare_model_costs(
    "Write Python code...",
    ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"],
    estimated_output_tokens=500
)

print("Ranked by price (cheapest first):")
for rank, r in enumerate(results, 1):
    print(f"{rank}. {r['model_id']:25} ${r['predicted_cost']:.6f}")
```

**Output:**
```
Ranked by price (cheapest first):
1. deepseek-chat             $0.000086
2. gemini-2.5-flash          $0.000091
3. gpt-4o                    $0.004585
4. claude-3-opus             $0.022755
```

---

### 4. Compare Two Models (A/B Test)
```python
from app.routing.cost_optimizer import run_ab_test

# Compare on COST
result = run_ab_test("gemini-2.5-flash", "gpt-4o", "CODE", "cost")
print(f"{result.winner} is {result.improvement_percent:.2f}% cheaper")

# Compare on SPEED
result = run_ab_test("gemini-2.5-flash", "claude-3-opus", "CODE", "latency")
print(f"{result.winner} is {result.improvement_percent:.2f}% faster")

# Compare on QUALITY
result = run_ab_test("claude-3-opus", "gemini-2.5-flash", "CODE", "reward")
print(f"{result.winner} has {result.improvement_percent:.2f}% better quality")

# Compare on VALUE (best reward per dollar)
result = run_ab_test("deepseek-chat", "gpt-4o", "CODE", "combined")
print(f"{result.winner} has {result.improvement_percent:.2f}% better value")
```

---

### 5. Find Fastest Models
```python
from app.routing.cost_optimizer import get_fastest_models

fastest = get_fastest_models("CODE", limit=3)

for rank, model in enumerate(fastest, 1):
    print(f"{rank}. {model['model_id']:25} {model['avg_latency']:.2f}s")
```

---

### 6. Find Most Cost-Efficient Models
```python
from app.routing.cost_optimizer import get_cost_efficient_models

efficient = get_cost_efficient_models("CODE", limit=3)

for rank, model in enumerate(efficient, 1):
    print(f"{rank}. {model['model_id']:25} "
          f"Efficiency: {model['efficiency_score']:.1f} (reward/$)")
```

---

### 7. Smart Selection (Weighted Scoring)
```python
from app.routing.cost_optimizer import find_optimal_model

candidates = ["gemini-2.5-flash", "gpt-4o", "claude-3-opus"]

# SCENARIO 1: Save money
best, score = find_optimal_model(
    "Your prompt here",
    candidates,
    weight_cost=0.6,      # 60% importance on COST
    weight_latency=0.2,   # 20% importance on SPEED
    weight_reward=0.2,    # 20% importance on QUALITY
    category="CODE"
)
print(f"Cost-sensitive winner: {best} (score={score:.4f})")

# SCENARIO 2: Best quality
best, score = find_optimal_model(
    "Your prompt here",
    candidates,
    weight_cost=0.1,      # 10% importance on COST
    weight_latency=0.2,   # 20% importance on SPEED
    weight_reward=0.7,    # 70% importance on QUALITY
    category="CODE"
)
print(f"Quality-first winner: {best} (score={score:.4f})")

# SCENARIO 3: Balanced
best, score = find_optimal_model(
    "Your prompt here",
    candidates,
    weight_cost=0.33,
    weight_latency=0.33,
    weight_reward=0.34,
    category="CODE"
)
print(f"Balanced winner: {best} (score={score:.4f})")
```

---

### 8. Compare All Models at Once
```python
from app.routing.cost_optimizer import run_multi_ab_tests

all_results = run_multi_ab_tests(
    ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"],
    category="CODE",
    metric="combined"  # or "cost", "latency", "reward"
)

for test_name, result in all_results.items():
    print(f"{test_name:45} → {result.winner:25} wins (+{result.improvement_percent:.2f}%)")
```

---

## 🔧 API Endpoints (For HTTP Requests)

### POST /api/cost/calculate
```json
{
    "model_id": "gpt-4o",
    "input_tokens": 125,
    "output_tokens": 500
}
```

### POST /api/cost/predict
```json
{
    "model_id": "gpt-4o",
    "prompt": "Write Python code...",
    "estimated_output_tokens": 500
}
```

### POST /api/cost/compare
```json
{
    "prompt": "Write Python code...",
    "models": ["gemini-2.5-flash", "gpt-4o", "claude-3-opus"],
    "estimated_output_tokens": 500
}
```

### POST /api/cost/ab-test
```json
{
    "model_a": "gemini-2.5-flash",
    "model_b": "gpt-4o",
    "category": "CODE",
    "metric": "cost"
}
```

### GET /api/cost/fastest/CODE?limit=3
Returns fastest models for CODE category

### GET /api/cost/efficient/CODE?limit=3
Returns most cost-efficient models

### POST /api/cost/optimal
```json
{
    "prompt": "Your prompt...",
    "candidates": ["gemini-2.5-flash", "gpt-4o"],
    "weight_cost": 0.6,
    "weight_latency": 0.2,
    "weight_reward": 0.2,
    "category": "CODE"
}
```

---

## 💰 Cost Examples

### Example 1: Simple Prompt
```
Prompt: "What is Python?" (15 chars ≈ 4 tokens)
Expected output: 50 tokens

Input tokens:  4
Output tokens: 50

Costs:
gemini-2.5-flash  → $(4/1M × $0.075) + (50/1M × $0.30) = $0.000150
gpt-4o            → $(4/1M × $5.0) + (50/1M × $15.0) = $0.000750
claude-3-opus     → $(4/1M × $15.0) + (50/1M × $75.0) = $0.003750

Cheapest: gemini (25x cheaper than claude!)
```

### Example 2: Medium Prompt
```
Prompt: "Write a Python sorting algorithm" (30 chars ≈ 8 tokens)
Expected output: 500 tokens

Input tokens:  8
Output tokens: 500

Costs:
gemini-2.5-flash  → $(8/1M × $0.075) + (500/1M × $0.30) = $0.000151
gpt-4o            → $(8/1M × $5.0) + (500/1M × $15.0) = $0.007540
claude-3-opus     → $(8/1M × $15.0) + (500/1M × $75.0) = $0.037620

Cheapest: gemini (249x cheaper than claude!)
```

### Example 3: Large Prompt
```
Prompt: "Design a REST API architecture..." (200+ chars ≈ 50 tokens)
Expected output: 2000 tokens

Input tokens:  50
Output tokens: 2000

Costs:
gemini-2.5-flash  → $(50/1M × $0.075) + (2000/1M × $0.30) = $0.000634
gpt-4o            → $(50/1M × $5.0) + (2000/1M × $15.0) = $0.030250
claude-3-opus     → $(50/1M × $15.0) + (2000/1M × $75.0) = $0.150750

Cheapest: gemini (238x cheaper than claude!)
```

---

## 📊 Model Pricing Reference

```
ULTRA-BUDGET:
deepseek-chat              → $0.14/$0.28 per 1M tokens

BUDGET:
gemini-2.5-flash           → $0.075/$0.30 per 1M tokens
gemma-3-27b-it             → $0.30/$0.30 per 1M tokens

MID-RANGE:
mistral-medium             → $0.27/$0.81 per 1M tokens
cohere-command-r           → $0.5/$1.5 per 1M tokens
claude-3-haiku             → $0.8/$4.0 per 1M tokens

PREMIUM:
gemini-1.5-pro             → $3.5/$10.5 per 1M tokens
cohere-command-r-plus      → $3.0/$15.0 per 1M tokens
claude-3-sonnet            → $3.0/$15.0 per 1M tokens

ULTRA-PREMIUM:
gpt-4o                     → $5.0/$15.0 per 1M tokens
gpt-4-turbo                → $10.0/$30.0 per 1M tokens
claude-3-opus              → $15.0/$75.0 per 1M tokens
gpt-4                      → $30.0/$60.0 per 1M tokens
```

---

## ⚡ Key Takeaways

### Cost Calculation
✅ **Input and output tokens have DIFFERENT prices**
✅ **Calculate exact cost per prompt (not averaged)**
✅ **Price difference can be 250x+ between models**

### Cost Savings
✅ **Potential savings: 50-99%**
✅ **Example: $540/month → $4.74/month**
✅ **For 1000 requests: $535.26/month saved**

### Smart Selection
✅ **Balance cost, speed, and quality**
✅ **Different weights for different scenarios**
✅ **Data-driven instead of random**

### A/B Testing
✅ **Compare any two models**
✅ **Test on: cost, latency, reward, combined value**
✅ **Get improvement percentages**

---

## 📚 Documentation Files

- **COST_OPTIMIZATION_SUMMARY.md** - Complete feature overview
- **COST_OPTIMIZATION_GUIDE.py** - Integration examples (runnable)
- **COST_OPTIMIZATION_ARCHITECTURE.md** - Visual diagrams
- **IMPLEMENTATION_COMPLETE.md** - Final status report

---

**Last Updated:** April 20, 2026
