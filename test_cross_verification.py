#!/usr/bin/env python3
"""
CROSS-VERIFICATION: Test hybrid router with diverse prompts (Windows-compatible)
Tests classification accuracy and confidence across different category types
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Set output encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from router import classify_with_fallback

# Comprehensive test prompts across all 11 categories
VERIFICATION_PROMPTS = {
    "CODE": [
        "Write a Python function to calculate Fibonacci numbers",
        "Debug this JavaScript async/await code",
        "How do I implement quicksort in C++?",
        "Fix the SQL query that's timing out",
        "Create a REST API endpoint in FastAPI",
    ],
    "ANALYSIS": [
        "Analyze the economic impact of inflation",
        "Compare machine learning algorithms",
        "Break down the causes of climate change",
        "Explain quantum mechanics principles",
        "What are the pros and cons of cryptocurrency?",
    ],
    "CHAT": [
        "Hello, how are you?",
        "Tell me a joke",
        "What's your opinion on AI?",
        "Let's talk about movies",
        "How was your day?",
    ],
    "CREATIVE": [
        "Write a short poem about love",
        "Create a story about time travel",
        "Compose song lyrics for a rock ballad",
        "Write a funny dialogue between two characters",
        "Create a fantasy world with unique magic system",
    ],
    "EXTRACTION": [
        "Extract all email addresses from this CSV",
        "Pull out key dates from this historical text",
        "Summarize the main points from this article",
        "List all the tasks and deadlines from this document",
        "Find all product names and prices from this catalog",
    ],
    "UTILITY": [
        "Convert 100 pounds to kilograms",
        "What's the capital of Australia?",
        "Calculate 25% of 480",
        "Translate 'thank you' to French",
        "What time is it in Tokyo right now?",
    ],
    "AGENTS": [
        "Search the web for latest Bitcoin price",
        "Check the weather forecast for New York",
        "Find the cheapest flight to Paris",
        "Look up contact info for Amazon support",
        "Search for the best pizza restaurants near me",
    ],
    "IMAGE": [
        "Generate a futuristic cityscape",
        "Create an image of a serene mountain landscape",
        "Design a logo for my tech startup",
        "Generate portrait in Van Gogh style",
        "Create an illustration of underwater creatures",
    ],
    "VIDEO": [
        "Create a tutorial video on how to cook pasta",
        "Generate a promotional video for my product",
        "Make a time-lapse video of city traffic",
        "Create an animated explainer for machine learning",
        "Generate a music video with special effects",
    ],
    "AUDIO": [
        "Generate a podcast intro for tech discussion",
        "Create background music for a meditation app",
        "Generate a voice-over for my presentation",
        "Create sound effects for a video game",
        "Generate a narration for my audiobook chapter",
    ],
    "MULTIMODAL": [
        "Create an interactive infographic about climate data",
        "Design a web page with images, text and animations",
        "Create a presentation combining charts and videos",
        "Generate a multimedia story with text, images and audio",
        "Create an interactive dashboard with visualizations",
    ],
}

def test_cross_verification():
    """Run cross-verification tests across all categories"""
    
    print("\n" + "="*120)
    print("CROSS-VERIFICATION TEST - Testing All Categories")
    print("="*120)
    
    total_tests = 0
    correct_tests = 0
    fast_path_total = 0
    safe_path_total = 0
    total_cost = 0
    
    category_results = {}
    
    for expected_category in sorted(VERIFICATION_PROMPTS.keys()):
        prompts = VERIFICATION_PROMPTS[expected_category]
        category_correct = 0
        category_fast = 0
        category_total = len(prompts)
        
        print(f"\n{'='*120}")
        print(f"CATEGORY: {expected_category}")
        print(f"{'='*120}")
        
        for i, prompt in enumerate(prompts, 1):
            result = classify_with_fallback(prompt)
            
            predicted = result["category"]
            confidence = result["confidence"]
            path = result["path"]
            cost = 0.00 if result["cost"] == "$0.00" else 0.004
            
            is_correct = predicted == expected_category
            status = "[OK]" if is_correct else "[FAIL]"
            
            if is_correct:
                category_correct += 1
                correct_tests += 1
            
            if path == "FAST":
                category_fast += 1
                fast_path_total += 1
            elif path == "SAFE":
                safe_path_total += 1
            
            total_tests += 1
            total_cost += cost
            
            path_icon = "[FAST]" if path == "FAST" else "[SAFE]" if path == "SAFE" else "[ERR]"
            print(f"  {i}. {status} {path_icon} {predicted:12} (conf: {confidence:.0%}) | {prompt[:60]}")
        
        accuracy = (category_correct / category_total) * 100
        fast_ratio = (category_fast / category_total) * 100
        
        category_results[expected_category] = {
            "correct": category_correct,
            "total": category_total,
            "accuracy": accuracy,
            "fast_path": category_fast,
            "fast_ratio": fast_ratio,
        }
        
        print(f"\n  ➜ Accuracy: {accuracy:.0f}% | Fast path: {fast_ratio:.0f}% ({category_fast}/{category_total})")
    
    # Summary Report
    print("\n" + "="*120)
    print("CROSS-VERIFICATION SUMMARY REPORT")
    print("="*120)
    
    overall_accuracy = (correct_tests / total_tests) * 100
    overall_fast_ratio = (fast_path_total / total_tests) * 100
    
    print(f"\nOVERALL METRICS:")
    print(f"  • Total Tests: {total_tests}")
    print(f"  • Correct: {correct_tests}/{total_tests} ({overall_accuracy:.1f}%)")
    print(f"  • FAST Path: {fast_path_total}/{total_tests} ({overall_fast_ratio:.1f}%)")
    print(f"  • SAFE Path: {safe_path_total}/{total_tests} ({100-overall_fast_ratio:.1f}%)")
    print(f"  • Total Cost: ${total_cost:.4f} (avg: ${total_cost/total_tests:.4f}/request)")
    
    print(f"\nPER-CATEGORY BREAKDOWN:")
    print(f"{'Category':<15} | {'Accuracy':<10} | {'Correct':<8} | {'Fast Path':<10}")
    print("-" * 55)
    
    for category in sorted(category_results.keys()):
        result = category_results[category]
        print(f"{category:<15} | {result['accuracy']:>8.0f}% | {result['correct']:>6}/{result['total']:<1} | {result['fast_ratio']:>8.0f}%")
    
    print(f"\nKEY INSIGHTS:")
    
    # Find best and worst categories
    best_cat = max(category_results.items(), key=lambda x: x[1]["accuracy"])
    worst_cat = min(category_results.items(), key=lambda x: x[1]["accuracy"])
    most_fast = max(category_results.items(), key=lambda x: x[1]["fast_ratio"])
    
    print(f"  ✅ Best Category: {best_cat[0]} ({best_cat[1]['accuracy']:.0f}% accuracy)")
    print(f"  ⚠️  Weak Category: {worst_cat[0]} ({worst_cat[1]['accuracy']:.0f}% accuracy)")
    print(f"  ⚡ Fastest Category: {most_fast[0]} ({most_fast[1]['fast_ratio']:.0f}% use FAST path)")
    
    # Recommendations
    print(f"\nRECOMMENDATIONS:")
    
    if overall_accuracy >= 85:
        print(f"""
  [SUCCESS] EXCELLENT PERFORMANCE
  
  {overall_accuracy:.1f}% overall accuracy is excellent! Hybrid approach working well.
  
  High-confidence categories (100% FAST path):""")
        for cat, data in category_results.items():
            if data['fast_ratio'] == 100:
                print(f"    - {cat}: Always use FAST path (100% accurate)")
        
        print(f"""
  Strategy: Keep using fast local classifier for all high-confidence categories.
  
  RECOMMENDATION: DEPLOY TO PRODUCTION - READY
""")
    
    elif overall_accuracy >= 75:
        print(f"""
  [CAUTION] ACCEPTABLE PERFORMANCE
  
  {overall_accuracy:.1f}% accuracy is acceptable with confidence thresholding.
  
  RECOMMENDATION: DEPLOY WITH MONITORING
  - Monitor weak categories ({worst_cat[0]})
  - Improve confidence thresholds
  - Retrain category embeddings if needed
""")
    
    else:
        print(f"""
  [WARNING] NEEDS IMPROVEMENT
  
  {overall_accuracy:.1f}% accuracy is below target.
  
  RECOMMENDATION: IMPROVE BEFORE PRODUCTION
  - Investigate weak categories
  - Adjust confidence threshold
  - Consider increasing training data
""")
    
    print("="*120 + "\n")

if __name__ == "__main__":
    test_cross_verification()
