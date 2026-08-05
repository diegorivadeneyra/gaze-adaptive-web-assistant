import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"


def analyze_text(text):

    prompt = f"""
Analyze the following text.

Return ONLY a JSON object.

Example:

{{
    "concept":"...",
    "complexity":"Low/Medium/High",
    "needs_assistance":true,
    "explanation":"..."
}}

Text:

{text}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "phi3",
            "prompt": prompt,
            "stream": False
        }
    )

    response_text = response.json()["response"]

    analysis = json.loads(response_text)

    return analysis