from __future__ import annotations

import json

import httpx

from app.config import get_settings

SYSTEM_PROMPT = """\
You are a recruiting data assistant for Cornell Athletics. The user will describe a recruit in natural language.

Extract and enrich the recruit's information. Return ONLY valid JSON:

{
  "name": "Full Name",
  "grad_year": "graduation year or null",
  "weight_class": "weight class or null",
  "home_town": "City, ST format or null",
  "guardian_email": "email or null",
  "source_url": "any URL mentioned or null",
  "sport": "sport if mentioned or null",
  "reply": "short friendly confirmation of what you captured"
}

Rules:
- Always use "City, ST" format for home_town (2-letter state code). Infer the state if only a city is given and it's unambiguous.
- If a high school name is mentioned, try to infer the city/state from it.
- If the user gives partial info, extract what you can and ask about the rest in "reply".
- Be concise in "reply" — just confirm what you got and note anything missing.
- If updating a previous recruit (conversation has history), merge new info with old.
"""


def extract_recruit(
    user_message: str,
    conversation_history: list[dict] | None = None,
    sport_context: str = "",
) -> dict:
    settings = get_settings()
    if not settings.perplexity_api_key:
        return {"error": "Perplexity API key not configured"}

    # Build a single user prompt that includes any prior context
    # Perplexity sonar requires strict system/user alternation,
    # so we collapse history into one user message instead.
    parts = []
    if conversation_history:
        for msg in conversation_history:
            role = msg.get("role", "user")
            parts.append(f"[{role}]: {msg.get('content', '')}")
        parts.append("")

    prompt = user_message
    if sport_context:
        prompt = f"[Sport: {sport_context}] {prompt}"
    parts.append(prompt)

    combined = "\n".join(parts)

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": combined},
                ],
                "temperature": 0.1,
            },
        )
        if resp.status_code != 200:
            return {"error": f"Perplexity API error ({resp.status_code}): {resp.text[:200]}"}

    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"reply": content, "name": None}
