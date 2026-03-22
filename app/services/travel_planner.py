from __future__ import annotations

from tavily import TavilyClient

from app.config import get_settings


def suggest_hotel(event_location: str, venue: str) -> tuple[str, str]:
    settings = get_settings()
    if not settings.tavily_api_key:
        label = "Team Hotel (manual verification needed)"
        location = f"{venue or event_location} area"
        return label, location

    query = (
        f"Best team-travel friendly hotel near {venue or event_location} "
        f"in {event_location}. Include full street address."
    )
    client = TavilyClient(api_key=settings.tavily_api_key)
    result = client.search(query=query, search_depth="advanced", max_results=3)
    results = result.get("results", [])
    if not results:
        return "Team Hotel (manual verification needed)", f"{venue or event_location} area"
    top = results[0]
    return top.get("title", "Team Hotel"), top.get("url", event_location)
