import requests
import logging
from app.core.config import settings

def call_azure_openai_api(messages, max_tokens=200, temperature=1, tools=None, tool_choice=None):
    try:
        if not settings.AZURE_OPENAI_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            logging.error("Azure OpenAI Key or Endpoint is incomplete in settings.")
            return None

        # Build the Azure OpenAI REST URL
        url = f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{settings.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME}/chat/completions?api-version={settings.AZURE_OPENAI_API_VERSION}"
        
        headers = {
            "api-key": settings.AZURE_OPENAI_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature
        }
        
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
            
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Azure OpenAI API Error ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        logging.error(f"Azure OpenAI Connection Error: {e}")
        return None
