# AI Router Pipeline V1.0

A resilient AI model router with local DeBERTa-v3 classification, semantic vault caching, and automated multi-provider fallbacks.

## 🚀 Getting Started

### 1. Prerequisites (Crucial)
Because this project uses **Git LFS** to store the 539MB local AI model weights, your friends **MUST** have Git LFS installed before cloning, or the model files will appear as tiny 1KB text pointers.

**Install Git LFS:**
- **Windows**: `git lfs install`
- **Mac**: `brew install git-lfs` && `git lfs install`
- **Linux**: `sudo apt install git-lfs` && `git lfs install`

### 2. Cloning the Repo
```bash
# Regular clone
git clone <your-repo-url>
cd <repo-name>

# Ensure the large model files are actually downloaded
git lfs pull
```

### 3. Setup & Installation
```bash
# Create and activate virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 4. Configuration
Create a `.env` file in the root directory:
```env
DATABASE_URL=your_postgresql_url
GEMINI_API_KEY=your_google_ai_key
ANTHROPIC_API_KEY=your_anthropic_key (optional)
OPENAI_API_KEY=your_openai_key (optional)
```

### 5. Running the API
```bash
uvicorn app.main:app --reload
```

## 🧠 Key Features
- **Local Routing**: Uses a fine-tuned DeBERTa-v3 model to classify prompts offline (0ms API latency).
- **Semantic Vault**: Automatically caches previous AI responses in PostgreSQL + Redis based on semantic similarity.
- **Failover Logic**: Automatically cycles through 3 fallback candidates if a high-tier provider returns a 404, 503, or 429 error.
- **Heuristic Intent Detection**: Automatically detects "Multi-step" logic in prompts and routes them to advanced generalist models.
