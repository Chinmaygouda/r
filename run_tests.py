import requests
import json
import time

API_URL = "http://127.0.0.1:8080/ask/stream"

def test_router(prompt, description):
    print(f"\n{'='*50}\nTESTING: {description}\nPROMPT: '{prompt}'\n{'-'*50}")
    
    payload = {
        "user_id": "test_script",
        "prompt": prompt,
        "user_tier": 1,
        "model_id": "auto",
        "provider": "TokenShield AI Router",
        "optimizations": {"compression": True, "thompson_sampling": True},
        "system_prompt": None,
        "api_keys": None
    }
    
    try:
        start_time = time.time()
        # Ensure streaming response is read completely
        with requests.post(API_URL, json=payload, stream=True) as response:
            if response.status_code != 200:
                print(f"ERROR: Status {response.status_code}")
                print(response.text)
                return False

            full_response = ""
            metrics = None
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data = decoded_line[6:]
                        if data == "[DONE]":
                            break
                        if data.startswith("[METRICS]"):
                            metrics = json.loads(data.replace("[METRICS]", "").strip())
                        elif data.startswith("[ERROR]"):
                            print(f"API Error: {data}")
                        else:
                            full_response += data
                            
        latency = time.time() - start_time
        print(f"Response: {full_response[:100]}...\n")
        print("METRICS:")
        if metrics:
            print(f"  - Model Used: {metrics.get('modelId')} ({metrics.get('provider')})")
            print(f"  - Input Tokens: {metrics.get('inputTokens')}")
            print(f"  - Output Tokens: {metrics.get('outputTokens')}")
            print(f"  - Cache Hit: {metrics.get('cacheHit')}")
            print(f"  - Latency: {latency:.2f}s")
        else:
            print("  No metrics received.")
        return True
    except Exception as e:
        print(f"Request failed: {e}")
        return False

print("Starting Deep Analysis Tests...")

# 1. Low Complexity Request (Should route to Budget model like Gemini Flash or Kimi)
test_router("What is the capital of France?", "Low Complexity Request")

# 2. High Complexity Request (Should route to Premium model like Claude Opus or GPT-4, or Nemotron/Llama 3.3 70B depending on config)
test_router("Explain the mathematical difference between Transformer attention mechanisms and State Space Models (Mamba) for sequence modeling, specifically analyzing computational complexity O(N^2) vs O(N).", "High Complexity Request")

# 3. Cache/Vault Test (Repeat the first question to see if we get a cache hit)
test_router("What is the capital of France?", "Cache/Vault Repeat Query")

print("\nTests Completed.")
