import os
import csv
import sys
import json
from google import genai
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CATEGORIES = [
    "CODE", "ANALYSIS", "CHAT", "CREATIVE", 
    "EXTRACTION", "UTILITY", "AGENTS"
]

SAMPLES_PER_CATEGORY = 50

def generate_synthetic_prompts(category: str, count: int) -> list:
    """Uses Gemini to generate perfectly diverse prompts for our golden dataset."""
    print(f"Generating {count} synthetic prompts for category: {category}...")
    
    prompt = f"""
    You are building a dataset to train a sequence classification model.
    Generate exactly {count} highly diverse, distinct user prompts that perfectly belong to the category '{category}'.
    
    Category definitions:
    - CODE: programming, debugging, writing software
    - ANALYSIS: explaining data, finding patterns, deep reasoning
    - CHAT: casual conversation, greetings, simple facts
    - CREATIVE: writing poems, stories, novels, brainstorming
    - EXTRACTION: pulling specific info out of text, formatting JSON
    - UTILITY: calculating math, converting formats, string manipulation
    - AGENTS: orchestrating tasks, multi-step planning, tool use
    
    Make the prompts realistic, varying from 1 sentence to 4 sentences. 
    Some should be polite, some demanding, some extremely complex, some simple.
    
    Return the response strictly as a JSON array of strings. 
    Example: ["Refactor this python script to use async", "Why is my docker container crashing on startup?"]
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        # Clean the response to ensure nice JSON
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]
            
        prompts = json.loads(text.strip())
        return prompts
    except Exception as e:
        print(f"Error generating for {category}: {e}")
        return []

def extract_from_db():
    from database.session import SessionLocal
    from app.models import UserConversation
    
    db = SessionLocal()
    prompts = []
    try:
        conversations = db.query(UserConversation).limit(1000).all()
        for idx, conv in enumerate(conversations):
            # To actually label them, we'd need to run them through the Gemini Router Prompt
            # For this script, we'll suggest using pure synthetic data for speed if DB is empty
            prompts.append(conv.prompt)
    finally:
        db.close()
    return prompts

if __name__ == "__main__":
    output_path = os.path.join(os.path.dirname(__file__), "training_data.csv")
    
    dataset = []
    
    print("Starting Data Harvesting Phase...")
    print("Strategy: Generating perfectly balanced synthetic dataset using Gemini 2.5 Flash")
    
    for category in CATEGORIES:
        prompts = generate_synthetic_prompts(category, SAMPLES_PER_CATEGORY)
        for p in prompts:
            dataset.append([p, category])
            
    # Save to CSV using basic formatting
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerows(dataset)
        
    print(f"\n✅ Successfully generated {len(dataset)} perfectly balanced prompts!")
    print(f"✅ Data saved to {output_path}")
    print("You are now ready to run the Google Colab Training Notebook.")
