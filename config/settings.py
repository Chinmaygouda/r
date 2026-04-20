"""
Configuration settings for the router system.
"""

# Routing confidence threshold
# If confidence >= CONFIDENCE_THRESHOLD → auto-select best model
# If confidence < CONFIDENCE_THRESHOLD → call bandit for exploration
CONFIDENCE_THRESHOLD = 0.5

# Number of top models to keep as candidates
TOP_K = 2

# Tier rules based on complexity level
# Determines which tiers are allowed for each complexity level
TIER_RULES = {
    "EASY": [2, 3],      # Simple tasks (1.0-5.5): Use Tier 2, 3
    "MEDIUM": [1, 2],    # Medium tasks (5.5-7.5): Use Tier 1B, Tier 2
    "HARD": [1]          # Hard tasks (7.5-10.0): Use Tier 1A, 1B only
}

# Complexity boundaries with tier mapping
# EASY (1.0-5.5): Tier 2, Tier 3 for budget/standard models
# MEDIUM (5.5-7.5): Tier 1B, Tier 2 for complex tasks requiring premium support
# HARD (7.5-10.0): Tier 1A, Tier 1B for ultra-complex requiring top models
COMPLEXITY_BOUNDARIES = {
    "EASY": (1.0, 5.5),
    "MEDIUM": (5.5, 7.5),
    "HARD": (7.5, 10.0)
}

# Sub-tier complexity mapping (refined tier distribution)
# Tier 1 A: Ultra-complex tasks (8.0-9.8) - top 3 models
# Tier 1 B: Complex tasks (7.5-9.5) - premium standard models
# Tier 2: Medium tasks (5.5-7.5) - standard models
# Tier 3: Simple tasks (1.0-5.5) - budget models
TIER_COMPLEXITY_MAP = {
    "TIER_1_A": {"min": 8.0, "max": 9.8, "sub_tier": "A"},
    "TIER_1_B": {"min": 7.5, "max": 9.5, "sub_tier": "B"},
    "TIER_2": {"min": 5.5, "max": 7.5, "sub_tier": None},
    "TIER_3": {"min": 1.0, "max": 5.5, "sub_tier": None}
}
