import requests
import json
import os
import time
import google.generativeai as genai
from typing import Dict, List, Tuple

class LLMClient:
    def __init__(self, config: dict):
        self.provider = config.get("llm", "ollama")
        self.max_risk = config.get("simulation", {}).get("max_risk_per_trade_percentage", 2.0)
        
        if self.provider == "gemini":
            gemini_config = config.get("gemini", {})
            self.model_name = gemini_config.get("model", "gemini-3.1-flash-lite")
            
            # The API key could be in GEMINI_API_KEY or GOOGLE_API_KEY
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
                
            # Clean string entirely of spaces or newlines that might cause gRPC illegal metadata errors
            api_key = "".join(api_key.split())
            
            if not api_key:
                raise ValueError("API Key for Gemini not found! Please ensure GOOGLE_API_KEY or GEMINI_API_KEY is set in your .env file.")
                
            genai.configure(api_key=api_key)
            
            self.gemini_model = genai.GenerativeModel(self.model_name)
        else:
            ollama_config = config.get("ollama", {})
            self.url = ollama_config.get("url", "http://localhost:11434")
            self.model_name = ollama_config.get("model", "gemma4-12b-Q8")
            self.api_endpoint = f"{self.url}/api/generate"

    def generate_decision(self, window: List[Dict], portfolio_state: Dict) -> Tuple[str, str, str]:
        """
        Sends data to Ollama and returns the decision.
        Returns: (decision, full_prompt, raw_response)
        decision will be one of: WAIT, BUY, SELL, CLOSE
        """
        
        system_prompt = f"""You are an expert algorithmic scalping trading AI that follows trends and momentum.
Your task is to analyze the provided recent candlestick data and current portfolio state to make a single trading decision.
The maximum allowed risk per trade is {self.max_risk}%.
You MUST output EXACTLY ONE of the following words as your decision:
WAIT
BUY
SELL
CLOSE

Do NOT output explanations, reasons, or JSON. Just the word.
"""

        user_content = {
            "portfolio_state": portfolio_state,
            "recent_candles": window
        }

        user_prompt = json.dumps(user_content, indent=2)

        prompt = f"{system_prompt}\n\nCurrent State:\n{user_prompt}\n\nDECISION:"

        if self.provider == "gemini":
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    response = self.gemini_model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.1,
                            max_output_tokens=10
                        )
                    )
                    raw_text = response.text.strip().upper()
                    return self._parse_decision(raw_text), prompt, raw_text
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "Quota" in error_str:
                        print(f"\n[!] Gemini Rate Limit (429) hit. Pausing for 35 seconds... (Attempt {attempt+1}/{max_retries})")
                        time.sleep(35)
                        continue
                    else:
                        print(f"Gemini API Error: {e}")
                        return "WAIT", prompt, error_str
                        
            print("\n[!] Max retries reached for Gemini API. Skipping inference.")
            return "WAIT", prompt, "RATE_LIMIT_EXCEEDED_AFTER_RETRIES"
        else:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 10
                }
            }
            try:
                response = requests.post(self.api_endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_text = data.get("response", "").strip().upper()
                return self._parse_decision(raw_text), prompt, raw_text
            except Exception as e:
                print(f"Ollama API Error: {e}")
                return "WAIT", prompt, str(e)

    def _parse_decision(self, raw_text: str) -> str:
        if "BUY" in raw_text:
            return "BUY"
        elif "SELL" in raw_text:
            return "SELL"
        elif "CLOSE" in raw_text:
            return "CLOSE"
        return "WAIT"
