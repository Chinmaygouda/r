import os
import sys
import pandas as pd
from termcolor import colored

# Force UTF-8 for Windows compatibility
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.routing.deberta_classifier import get_semantic_classifier

def run_evaluation():
    csv_path = os.path.join(os.path.dirname(__file__), 'training_data.csv')
    
    if not os.path.exists(csv_path):
        print(f"❌ Error: {csv_path} not found.")
        return
        
    print("Loading dataset...")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows.")
    
    classifier = get_semantic_classifier()
    
    if classifier.classifier is None:
        print("❌ Error: Classifier could not be loaded.")
        return
    
    correct = 0
    total = len(df)
    
    print("\nEvaluating against training_data.csv...")
    for idx, row in df.iterrows():
        # Display progress every 100 rows to avoid console spam
        if (idx+1) % 100 == 0:
            print(f"Processed {idx+1}/{total}...")
            
        prompt = row['text']
        expected_category = row['label']
        
        try:
            # We only care about the category prediction for basic accuracy
            predicted_category, confidence = classifier.classify_prompt(prompt)
            if predicted_category == expected_category:
                correct += 1
        except Exception as e:
            print(f"Error on row {idx}: {e}")
            
    accuracy = (correct / total) * 100
    
    print("\n" + "="*50)
    print(colored("🎯 CROSS VERIFICATION COMPLETE", "cyan", attrs=["bold"]))
    print("="*50)
    print(f"Total Evaluated : {total}")
    print(f"Exact Matches   : {correct}")
    print(f"Accuracy        : {accuracy:.2f}%")
    print("="*50)

if __name__ == "__main__":
    run_evaluation()
