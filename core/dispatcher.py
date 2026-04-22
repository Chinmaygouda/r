#FROZEN CODE - DO NOT MODIFY

import os
from dotenv import load_dotenv
from openai import OpenAI
from google import genai

load_dotenv()

class Dispatcher:
    def __init__(self):
        # 1. Native SDKs - lazy load to avoid import errors
        self.client_anthropic = None
        self.client_cohere = None
        self.client_google = None
        
        # Google API configured at startup (optional)
        try:
            self.client_google = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        except:
            pass

        # 2. OpenAI-Compatible Hub - lazy load clients
        self.hub = {}

    def _get_hub_client(self, provider):
        """Lazily initialize and return OpenAI-compatible client."""
        if provider not in self.hub:
            hub_config = {
                "OpenAI": (os.getenv("OPENAI_API_KEY"), None),
                "xAI": (os.getenv("XAI_API_KEY"), "https://api.x.ai/v1"),
                "OpenRouter": (os.getenv("OPENROUTER_API_KEY"), "https://openrouter.ai/api/v1"),
                "Together": (os.getenv("TOGETHER_API_KEY"), "https://api.together.xyz/v1"),
                "DeepSeek": (os.getenv("DEEPSEEK_API_KEY"), "https://api.deepseek.com"),
                "Mistral": (os.getenv("MISTRAL_API_KEY"), "https://api.mistral.ai/v1"),
                "HuggingFace": (os.getenv("HUGGINGFACE_API_KEY"), "https://api-inference.huggingface.co/v1")
            }
            
            if provider in hub_config:
                api_key, base_url = hub_config[provider]
                if api_key:
                    try:
                        if base_url:
                            self.hub[provider] = OpenAI(api_key=api_key, base_url=base_url)
                        else:
                            self.hub[provider] = OpenAI(api_key=api_key)
                    except Exception as e:
                        return None
        
        return self.hub.get(provider)

    def execute(self, provider, model_id, prompt):
        """Standardized execution returning {'text': str, 'tokens': int, 'success': bool}"""
        try:
            # Route to OpenAI-Compatible Hub
            if provider in ["OpenAI", "xAI", "OpenRouter", "Together", "DeepSeek", "Mistral", "HuggingFace"]:
                client = self._get_hub_client(provider)
                if not client:
                    return {"text": f"Error: {provider} API key not configured.", "tokens": 0, "success": False}
                
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": prompt}]
                )
                return {
                    "text": response.choices[0].message.content,
                    "tokens": response.usage.total_tokens if response.usage else 0,
                    "success": True
                }

            # Route to Anthropic
            elif provider == "Anthropic":
                try:
                    from anthropic import Anthropic
                    if not self.client_anthropic:
                        self.client_anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                    response = self.client_anthropic.messages.create(
                        model=model_id,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    # Correct attribute names for Anthropic SDK
                    tokens = response.usage.input_tokens + response.usage.output_tokens
                    return {"text": response.content[0].text, "tokens": tokens, "success": True}
                except ImportError:
                    return {"text": "Error: Anthropic SDK not installed. Install with: pip install anthropic", "tokens": 0, "success": False}

            # Route to Google
            elif provider == "Google":
                if not self.client_google:
                    self.client_google = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                
                if self.client_google:
                    response = self.client_google.models.generate_content(
                        model=model_id,
                        contents=prompt
                    )
                    return {
                        "text": response.text,
                        "tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0,
                        "success": True
                    }
                else:
                    return {"text": "Error: Google API key not configured.", "tokens": 0, "success": False}

            # Route to Cohere
            elif provider == "Cohere":
                try:
                    import cohere
                    if not self.client_cohere:
                        co_key = os.getenv("COHERE_API_KEY")
                        self.client_cohere = cohere.Client(co_key) if co_key else None
                    
                    if self.client_cohere:
                        response = self.client_cohere.chat(model=model_id, message=prompt)
                        return {
                            "text": response.text, 
                            "tokens": response.meta.tokens.total_tokens if response.meta else 0,
                            "success": True
                        }
                    else:
                        return {"text": "Error: Cohere API key not configured.", "tokens": 0, "success": False}
                except ImportError:
                    return {"text": "Error: Cohere SDK not installed. Install with: pip install cohere", "tokens": 0, "success": False}

            # If no provider matches
            return {"text": f"Error: Provider '{provider}' not configured.", "tokens": 0, "success": False}

        except Exception as e:
            # Always return a dict even on error to prevent main.py from crashing
            return {"text": f"Execution Error [{provider}]: {str(e)}", "tokens": 0, "success": False}
