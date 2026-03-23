from __future__ import annotations

import json
import httpx

from app.config import get_settings


SYSTEM_PROMPT = """\
You are a travel planning assistant for Cornell Athletics. You help plan away game trips.

Given the user's message, extract whatever travel details they mention.
Return ONLY valid JSON with these fields (use null for anything not mentioned):

{
  "depart_date": "date string or null",
  "return_date": "date string or null",
  "transport_there": "fly / charter bus / drive / train or null",
  "transport_back": "fly / charter bus / drive / train or null",
  "people_per_room": number or null,
  "spend_limit_per_person": number or null,
  "total_spend_limit": number or null,
  "hotel_preferences": "any hotel preferences mentioned or null",
  "notes": "any other details mentioned or null",
  "missing": ["only list CRITICAL missing items - max 1-2"]
}

IMPORTANT rules for "missing":
- Only flag departure date or return date if NEITHER was provided
- Only flag transportation if not mentioned at all
- Do NOT ask about budget, rooming, hotel prefs, or other optional details
- Keep it to 1 item max. If you have dates and transport, missing should be empty.
- Be generous with inference. "$80 per guy" = spend_limit_per_person. "3 to a room" = people_per_room.
"""


def chat_plan(user_message: str, event_context: str) -> dict:
    settings = get_settings()
    if not settings.perplexity_api_key:
        return {"error": "Perplexity API key not configured"}

    prompt = f"Event context: {event_context}\n\nUser request: {user_message}"

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
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    return json.loads(content)


def search_hotels(location: str, dates: str, preferences: str) -> list[dict]:
    """Use Perplexity to search for real hotel options near the event."""
    settings = get_settings()
    if not settings.perplexity_api_key:
        return _mock_hotels(location)

    query = (
        f"Find 3 hotels near {location} for a college sports team trip {dates}. "
        f"Preferences: {preferences or 'team-friendly, close to venue'}. "
        "Return ONLY valid JSON array with objects: "
        '{"name": "...", "address": "...", "listed_price": number, "notes": "..."}. '
        "listed_price should be nightly rate in dollars. No markdown, no extra text."
    )

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        hotels = json.loads(content)
        # Add our negotiated price (demo: 15-25% off)
        import random
        for h in hotels:
            listed = h.get("listed_price", 180)
            discount = random.uniform(0.75, 0.85)
            h["our_price"] = round(listed * discount)
            h["listed_price"] = listed
        return hotels
    except Exception:
        return _mock_hotels(location)


def _mock_hotels(location: str) -> list[dict]:
    return [
        {"name": "Courtyard by Marriott", "address": f"Near {location}", "listed_price": 189, "our_price": 152, "notes": "Team rate available"},
        {"name": "Hampton Inn & Suites", "address": f"Near {location}", "listed_price": 169, "our_price": 139, "notes": "Free breakfast, pool"},
        {"name": "Holiday Inn Express", "address": f"Near {location}", "listed_price": 149, "our_price": 119, "notes": "Close to venue"},
    ]
