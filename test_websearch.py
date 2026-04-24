"""
Testa se a chave Anthropic tem acesso a web search.
Corre: python test_websearch.py
"""
import sys
sys.path.insert(0, ".")
import requests
from config import ANTHROPIC_API_KEY

print("\nA testar web search da Anthropic API...")

try:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 200,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                }
            ],
            "messages": [
                {"role": "user", "content": "Search for: IONQ stock news today"}
            ],
        },
        timeout=20,
    )

    if response.status_code == 200:
        data = response.json()
        # Verificar se usou web search
        used_search = any(
            block.get("type") == "tool_use" and block.get("name") == "web_search"
            for block in data.get("content", [])
        )
        if used_search:
            print("✅ Web search DISPONÍVEL — a chave tem acesso.")
        else:
            print("⚠️  API responde mas web search pode não ter sido usada.")
            print("   Resposta:", str(data.get("content", ""))[:200])

    elif response.status_code == 400:
        error = response.json().get("error", {})
        if "web_search" in str(error):
            print("❌ Web search NÃO disponível nesta chave.")
            print("   Vamos usar alternativa com yfinance + RSS.")
        else:
            print("❌ Erro 400:", error.get("message", ""))

    else:
        print("❌ Erro " + str(response.status_code) + ": " + response.text[:200])

except Exception as e:
    print("❌ Erro: " + str(e))

print()
