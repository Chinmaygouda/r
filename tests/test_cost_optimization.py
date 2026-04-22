"""
TEST: COST OPTIMIZATION, A/B TESTING, AND LATENCY OPTIMIZATION
Tests exact token-level pricing, cost prediction, and model comparison
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.routing.cost_optimizer import (
    calculate_exact_cost,
    predict_cost_for_prompt,
    compare_model_costs,
    get_fastest_models,
    get_cost_efficient_models,
    run_ab_test,
    run_multi_ab_tests,
    find_optimal_model,
    PROVIDER_PRICING
)
from database.db import update_model_performance
from database.session import SessionLocal
from app.models import ModelPerformance

print("\n" + "="*90)
print("[COST OPTIMIZATION, A/B TESTING & LATENCY OPTIMIZATION]")
print("="*90)

# ==================== TEST 1: EXACT TOKEN COST CALCULATION ====================
print("\n\n[TEST 1: EXACT TOKEN COST CALCULATION]")
print("-" * 90)

# Scenario: User prompt = 500 chars (~125 tokens), Model response = 2000 chars (~500 tokens)
input_tokens = 125
output_tokens = 500

models_to_test = ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"]

print("[SCENARIO] Input prompt: 125 tokens | Expected output: 500 tokens")
print("-" * 90)

for model_id in models_to_test:
    cost_data = calculate_exact_cost(model_id, input_tokens, output_tokens)
    
    print(f"\n{model_id:25}")
    print(f"  Input:   {cost_data['input_tokens']:6} tokens × ${PROVIDER_PRICING[model_id].input_cost_per_1m/1_000_000:.6f}/token = ${cost_data['input_cost']:.6f}")
    print(f"  Output:  {cost_data['output_tokens']:6} tokens × ${PROVIDER_PRICING[model_id].output_cost_per_1m/1_000_000:.6f}/token = ${cost_data['output_cost']:.6f}")
    print(f"  [TOTAL COST] ${cost_data['total_cost']:.6f}")

# ==================== TEST 2: COST PREDICTION FOR PROMPT ====================
print("\n\n[TEST 2: COST PREDICTION FOR PROMPT]")
print("-" * 90)

sample_prompts = {
    "short": "What is Python?",
    "medium": "Explain the concept of decorators in Python with 2 examples",
    "long": "Design a REST API architecture for a multi-tenant SaaS application. Include database schema, API endpoints, authentication, rate limiting, error handling, and deployment considerations."
}

print("[PREDICTION] Before execution, estimate cost for different prompt lengths\n")

for prompt_type, prompt_text in sample_prompts.items():
    print(f"\n{prompt_type.upper()} PROMPT ({len(prompt_text)} chars, ~{len(prompt_text)//4} tokens):")
    print(f"  \"{prompt_text[:60]}...\"")
    print("-" * 90)
    
    for model_id in ["gemini-2.5-flash", "gpt-4o", "claude-3-opus"]:
        prediction = predict_cost_for_prompt(model_id, prompt_text, estimated_output_tokens=500)
        print(f"  {model_id:25} → Predicted cost: ${prediction['total_cost']:.6f}")

# ==================== TEST 3: COST COMPARISON ====================
print("\n\n[TEST 3: COST COMPARISON (Rank models by price)]")
print("-" * 90)

test_prompt = "Write a Python function to sort a list of dictionaries by multiple keys"
comparison = compare_model_costs(test_prompt, models_to_test, estimated_output_tokens=300)

print(f"[PROMPT] '{test_prompt}'")
print(f"[EXPECTED OUTPUT] ~300 tokens\n")
print("Ranking (cheapest to most expensive):")
print("-" * 90)

for rank, result in enumerate(comparison, 1):
    savings = comparison[0]["predicted_cost"] - result["predicted_cost"]
    cost_diff = "baseline" if rank == 1 else f"+${result['predicted_cost'] - comparison[0]['predicted_cost']:.6f}"
    
    print(f"{rank}. {result['model_id']:25} ${result['predicted_cost']:.6f} {cost_diff}")

# ==================== TEST 4: SEED PERFORMANCE DATA ====================
print("\n\n[TEST 4: SEEDING PERFORMANCE DATA FOR A/B TESTS]")
print("-" * 90)

print("[SETUP] Creating mock performance data for testing...")

# Clear existing data
db = SessionLocal()
try:
    db.query(ModelPerformance).delete()
    db.commit()
    print("[OK] Cleared previous performance data")
except Exception as e:
    print(f"[WARN] Could not clear: {e}")
    db.rollback()
finally:
    db.close()

# Seed performance data
test_data = [
    ("gemini-2.5-flash", "CODE", 0.85, 0.00005, 1.2),
    ("gemini-2.5-flash", "CODE", 0.87, 0.00005, 1.1),
    ("gemini-2.5-flash", "CODE", 0.86, 0.00005, 1.3),
    
    ("gpt-4o", "CODE", 0.92, 0.00015, 2.5),
    ("gpt-4o", "CODE", 0.90, 0.00015, 2.3),
    ("gpt-4o", "CODE", 0.91, 0.00015, 2.4),
    
    ("claude-3-opus", "CODE", 0.95, 0.00025, 3.2),
    ("claude-3-opus", "CODE", 0.94, 0.00025, 3.1),
    ("claude-3-opus", "CODE", 0.96, 0.00025, 3.3),
    
    ("deepseek-chat", "CODE", 0.72, 0.00001, 4.5),
    ("deepseek-chat", "CODE", 0.74, 0.00001, 4.3),
    ("deepseek-chat", "CODE", 0.73, 0.00001, 4.6),
]

print(f"[SIMULATION] Adding {len(test_data)} performance records...")

for model_id, category, reward, cost, latency in test_data:
    result = update_model_performance(model_id, category, reward, cost, latency)
    print(f"  ✓ {model_id:25} (reward={reward:.2f}, cost=${cost:.6f}, latency={latency:.1f}s)")

print(f"[OK] Seeded {len(test_data)} records")

# ==================== TEST 5: A/B TESTING ====================
print("\n\n[TEST 5: A/B TESTING (Compare two models)]")
print("-" * 90)

test_pairs = [
    ("gemini-2.5-flash", "gpt-4o", "cost"),
    ("gpt-4o", "claude-3-opus", "latency"),
    ("gemini-2.5-flash", "deepseek-chat", "reward"),
    ("gpt-4o", "claude-3-opus", "combined"),
]

print("[A/B TESTS] Comparing model pairs on different metrics\n")

for model_a, model_b, metric in test_pairs:
    result = run_ab_test(model_a, model_b, "CODE", metric)
    
    if result:
        print(f"[{metric.upper()}] {model_a} vs {model_b}")
        print(f"  Winner: {result.winner}")
        print(f"  Performance: {result.winner_value:.6f} vs {result.loser_value:.6f}")
        print(f"  Improvement: {result.improvement_percent:.2f}%\n")

# ==================== TEST 6: MULTI A/B TEST ====================
print("\n[TEST 6: MULTI A/B TESTING (All pairs)]")
print("-" * 90)

models = ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"]
all_tests = run_multi_ab_tests(models, "CODE", "combined")

print(f"[COMBINED METRIC] Comparing {len(models)} models ({len(all_tests)} pairs)")
print("-" * 90)

for test_name, result in all_tests.items():
    print(f"{test_name:40} → Winner: {result.winner:25} (+{result.improvement_percent:.2f}%)")

# ==================== TEST 7: FASTEST MODELS ====================
print("\n\n[TEST 7: FASTEST MODELS BY LATENCY]")
print("-" * 90)

fastest = get_fastest_models("CODE", limit=3)
print("[RANKING] Models by latency (fastest first):\n")

for rank, model_info in enumerate(fastest, 1):
    print(f"{rank}. {model_info['model_id']:25} | Avg Latency: {model_info['avg_latency']:.2f}s | "
          f"Reward: {model_info['avg_reward']:.4f} | Selections: {model_info['selections']}")

# ==================== TEST 8: COST-EFFICIENT MODELS ====================
print("\n\n[TEST 8: COST-EFFICIENT MODELS (Reward per Dollar)]")
print("-" * 90)

efficient = get_cost_efficient_models("CODE", limit=3)
print("[RANKING] Models by cost-efficiency (best value first):\n")

for rank, model_info in enumerate(efficient, 1):
    print(f"{rank}. {model_info['model_id']:25} | Cost: ${model_info['avg_cost']:.6f} | "
          f"Reward: {model_info['avg_reward']:.4f} | Efficiency: {model_info['efficiency_score']:.4f} | "
          f"Selections: {model_info['selections']}")

# ==================== TEST 9: OPTIMAL MODEL SELECTION ====================
print("\n\n[TEST 9: HYBRID OPTIMIZATION (Weighted Scoring)]")
print("-" * 90)

print("[SCENARIO 1] Cost-sensitive (weight: cost=0.6, latency=0.2, reward=0.2)")
model_a, score_a = find_optimal_model(
    "Any prompt",
    ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"],
    weight_cost=0.6,
    weight_latency=0.2,
    weight_reward=0.2,
    category="CODE"
)
print(f"  → Best Model: {model_a:25} | Score: {score_a:.4f}")

print("\n[SCENARIO 2] Quality-first (weight: cost=0.1, latency=0.2, reward=0.7)")
model_b, score_b = find_optimal_model(
    "Any prompt",
    ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"],
    weight_cost=0.1,
    weight_latency=0.2,
    weight_reward=0.7,
    category="CODE"
)
print(f"  → Best Model: {model_b:25} | Score: {score_b:.4f}")

print("\n[SCENARIO 3] Balanced (weight: cost=0.33, latency=0.33, reward=0.34)")
model_c, score_c = find_optimal_model(
    "Any prompt",
    ["gemini-2.5-flash", "gpt-4o", "claude-3-opus", "deepseek-chat"],
    weight_cost=0.33,
    weight_latency=0.33,
    weight_reward=0.34,
    category="CODE"
)
print(f"  → Best Model: {model_c:25} | Score: {score_c:.4f}")

# ==================== SUMMARY ====================
print("\n\n" + "="*90)
print("[SUMMARY] COST OPTIMIZATION FEATURES")
print("="*90)

summary = """
✅ EXACT TOKEN COST CALCULATION
   - Separate input/output token pricing
   - Per-model pricing database
   - Calculates cost for EXACT prompt (not averaged)
   
✅ COST PREDICTION
   - Estimate cost BEFORE execution
   - Compare costs across models
   - Identify cheapest option

✅ LATENCY OPTIMIZATION
   - Rank models by average response time
   - Find fastest models for each category
   - Track performance improvements

✅ COST-EFFICIENCY RANKING
   - Calculate reward-per-dollar metric
   - Find best value models
   - Balance quality and cost

✅ A/B TESTING
   - Compare two models on any metric
   - Test all model pairs at once
   - Measure improvement percentage

✅ HYBRID OPTIMIZATION
   - Weighted scoring (cost + latency + reward)
   - Scenario-based selection
   - Cost-sensitive vs Quality-first strategies

[NEXT STEPS]
1. Integrate cost_optimizer into router for intelligent selection
2. Add cost prediction endpoint to API
3. Create dashboard showing A/B test results
4. Monitor cost savings over time
"""

print(summary)
print("="*90 + "\n")
