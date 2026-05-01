#FROZEN CODE - DO NOT MODIFY


import os
import hashlib
from datetime import datetime
from openai import OpenAI
from app.database_init import SessionLocal
from app.models import AIModel
from core.librarian import audit_models
from dotenv import load_dotenv

load_dotenv()

def get_base_url(provider):
    urls = {
        "OpenAI": "https://api.openai.com/v1",
        "NVIDIA": "https://integrate.api.nvidia.com/v1",
        "OpenRouter": "https://openrouter.ai/api/v1",
        "Together": "https://api.together.xyz/v1",
        "DeepSeek": "https://api.deepseek.com",
        "xAI": "https://api.x.ai/v1",
        "Mistral": "https://api.mistral.ai/v1",
        "HuggingFace": "https://api-inference.huggingface.co/v1"
    }
    return urls.get(provider)

def get_api_keys_hash():
    """Generate MD5 hash of current API keys for change detection."""
    keys = [
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("ANTHROPIC_API_KEY", ""),
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("COHERE_API_KEY", "")
    ]
    combined = "".join(keys)
    return hashlib.md5(combined.encode()).hexdigest()

def should_update_models():
    """Check if model update needed: (1) no discovered models, (2) 30+ days, or (3) API keys changed.
    
    BUG #8 FIX: Previously checked total model count, but main.py seeds 7 hardcoded models
    at startup which made count > 0, so the Librarian was never triggered.
    Now we check specifically for Librarian-discovered models (non-spacer, non-seed providers).
    """
    db = SessionLocal()
    SEED_PROVIDERS = {"---"}  # Spacer rows
    try:
        # Check 1: No Librarian-discovered models (ignore hardcoded seeds by checking last_audited)
        # Seed models have last_audited = NOW() at creation, so we check for models
        # that were added via the Librarian (which calls audit_models and sets no special flag).
        # The most reliable proxy: if ALL models share the exact same last_audited second, 
        # they were batch-seeded, not discovered.
        from sqlalchemy import func
        model_count = db.query(AIModel).filter(
            ~AIModel.model_id.startswith("---")
        ).count()
        
        if model_count == 0:
            print("📊 No models in database - triggering Librarian discovery...")
            return True
        
        # Check if ALL models are the hardcoded seed set (7 models with identical last_audited)
        distinct_audit_times = db.query(func.count(func.distinct(
            func.date_trunc('minute', AIModel.last_audited)
        ))).filter(~AIModel.model_id.startswith("---")).scalar()
        
        if distinct_audit_times <= 1 and model_count <= 10:
            print(f"📊 Only {model_count} seed/static models found - triggering Librarian discovery...")
            return True
        
        # Check 2: 30+ days since last audit
        latest = db.query(AIModel).order_by(AIModel.last_audited.desc()).first()
        if latest and latest.last_audited:
            days_since = (datetime.utcnow() - latest.last_audited).days
            if days_since >= 30:
                print(f"📅 30+ days since last audit ({days_since} days) - updating...")
                return True
        
        # Check 3: API keys changed
        hash_file = ".api_key_hash"
        current_hash = get_api_keys_hash()
        
        if os.path.exists(hash_file):
            with open(hash_file, "r") as f:
                stored_hash = f.read().strip()
            if current_hash != stored_hash:
                print("🔑 API keys changed - updating...")
                return True
        else:
            # First time - save hash
            with open(hash_file, "w") as f:
                f.write(current_hash)
        
        print("✅ Models up-to-date (30-day refresh not needed)")
        return False
    finally:
        db.close()

def discover_google_models():
    """Discover Google models via genai API."""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        models = []
        for m in client.models.list():
            if m.name:
                models.append(m.name.replace("models/", ""))
        return models
    except Exception as e:
        print(f"⚠️ Google discovery failed: {e}")
        return []

def discover_anthropic_models():
    """Discover Anthropic models via API call."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        # Anthropic doesn't expose models.list(), but we can query via messages endpoint
        # For now, make a test call to verify connection and get available model info
        models = []
        # Try to get models from their documentation endpoint if available
        import requests
        headers = {
            "anthropic-version": "2023-06-01",
            "x-api-key": os.getenv("ANTHROPIC_API_KEY")
        }
        response = requests.get("https://api.anthropic.com/v1/models", headers=headers)
        if response.status_code == 200:
            data = response.json()
            models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return models
    except Exception as e:
        print(f"⚠️ Anthropic discovery failed: {e}")
        return []

def discover_cohere_models():
    """Discover Cohere models via API call."""
    try:
        import cohere
        client = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))
        # Cohere doesn't expose a direct models.list() endpoint either
        # Make HTTP request to their models endpoint
        import requests
        headers = {
            "Authorization": f"Bearer {os.getenv('COHERE_API_KEY')}"
        }
        response = requests.get("https://api.cohere.com/v1/models", headers=headers)
        if response.status_code == 200:
            data = response.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return models
    except Exception as e:
        print(f"⚠️ Cohere discovery failed: {e}")
        return []

def run_30_day_refresh():
    db = SessionLocal()
    
    print("\n" + "="*70)
    print("🚀 AUTO-DISCOVERY: Discovering & Categorizing Models")
    print("="*70)
    
    all_discovered = {}
    
    # Discover from Google
    print("\n📡 [Google] Discovering models via genai API...")
    google_models = discover_google_models()
    if google_models:
        all_discovered["Google"] = google_models
        print(f"   ✅ Found {len(google_models)} Google models")
    
    # Discover from Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        print("\n📡 [Anthropic] Discovering models via API...")
        anthropic_models = discover_anthropic_models()
        if anthropic_models:
            all_discovered["Anthropic"] = anthropic_models
            print(f"   ✅ Found {len(anthropic_models)} Anthropic models")
        else:
            print(f"   ⚠️ No models returned from Anthropic API")
    else:
        print("\n📡 [Anthropic] No API key configured - skipping")
    
    # Discover from Cohere
    if os.getenv("COHERE_API_KEY"):
        print("\n📡 [Cohere] Discovering models via API...")
        cohere_models = discover_cohere_models()
        if cohere_models:
            all_discovered["Cohere"] = cohere_models
            print(f"   ✅ Found {len(cohere_models)} Cohere models")
        else:
            print(f"   ⚠️ No models returned from Cohere API")
    else:
        print("\n📡 [Cohere] No API key configured - skipping")
    
    # Discover from other providers using OpenAI-compatible API
    providers_to_check = {
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "NVIDIA": os.getenv("NVIDIA_API_KEY"),
        "OpenRouter": os.getenv("OPENROUTER_API_KEY"),
        "Together": os.getenv("TOGETHER_API_KEY"),
        "DeepSeek": os.getenv("DEEPSEEK_API_KEY"),
        "xAI": os.getenv("XAI_API_KEY"),
        "Mistral": os.getenv("MISTRAL_API_KEY"),
        "HuggingFace": os.getenv("HUGGINGFACE_API_KEY")
    }

    for name, key in providers_to_check.items():
        if not key: 
            print(f"\n📡 [{name}] No API key configured - skipping")
            continue
            
        print(f"\n📡 [{name}] Discovering models via OpenAI-compatible API...")
        try:
            client = OpenAI(api_key=key, base_url=get_base_url(name))
            available_models = [m.id for m in client.models.list()]
            
            if available_models:
                all_discovered[name] = available_models
                print(f"   ✅ Found {len(available_models)} {name} models")
            else:
                print(f"   ⚠️ No models returned from API")
        except Exception as e:
            print(f"   ⚠️ Discovery failed: {str(e)}")

    # Process each provider's models
    print("\n" + "-"*70)
    print("📝 Processing & Categorizing Models with AI")
    print("-"*70)
    
    for provider, models in all_discovered.items():
        print(f"\n🔄 Processing {provider}...")
        try:
            audit_models(provider, models)
        except Exception as e:
            print(f"   ⚠️ Error processing {provider}: {e}")
    
    # BUG #2 + #3 FIX: db.execute() with a raw string was removed in SQLAlchemy 2.0.
    # Also the table name was wrong: SQLAlchemy maps AIModel → table 'models', NOT 'ai_model'.
    try:
        from sqlalchemy import text
        db.execute(text("UPDATE models SET last_audited = NOW() WHERE model_id NOT LIKE '---%'"))
        db.commit()
        print("\n✅ Updated last_audited timestamps")
    except Exception as e:
        print(f"⚠️ Error updating timestamps: {e}")
        db.rollback()
    finally:
        db.close()
    
    # Save current API key hash
    hash_file = ".api_key_hash"
    current_hash = get_api_keys_hash()
    with open(hash_file, "w") as f:
        f.write(current_hash)
    print(f"✅ API key hash saved")
    
    print("\n" + "="*70)
    print("✅ AUTO-DISCOVERY COMPLETE")
    print("="*70 + "\n")

def run_auto_update():
    """Main orchestration: check if update needed → discover → categorize → store."""
    try:
        if should_update_models():
            run_30_day_refresh()
    except Exception as e:
        print(f"⚠️ Auto-discovery error: {e}")
