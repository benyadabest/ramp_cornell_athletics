from __future__ import annotations

import json
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from tavily import TavilyClient

from app.config import get_settings


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _fetch_url(url: str) -> str:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    return response.text


def _extract_table_rows(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for table in soup.select("table"):
        header_cells = [
            _clean(h.get_text(" ", strip=True)).lower() for h in table.select("thead th")
        ]
        for tr in table.select("tbody tr"):
            cells = [_clean(td.get_text(" ", strip=True)) for td in tr.select("td")]
            if not cells:
                continue
            row: dict[str, str] = {}
            if header_cells and len(header_cells) == len(cells):
                for idx, key in enumerate(header_cells):
                    row[key] = cells[idx]
            else:
                for idx, val in enumerate(cells):
                    row[f"col_{idx + 1}"] = val
            rows.append(row)
    return rows


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove scripts/style to reduce noisy tokens.
    for el in soup(["script", "style", "noscript"]):
        el.decompose()
    return soup.get_text("\n", strip=True)


def _tavily_fallback(url: str) -> str:
    settings = get_settings()
    if not settings.tavily_api_key:
        return ""
    client = TavilyClient(api_key=settings.tavily_api_key)
    result = client.search(
        query=f"Extract structured details from this athletics page: {url}",
        max_results=5,
        search_depth="advanced",
    )
    chunks = [url]
    for item in result.get("results", []):
        chunks.append(item.get("title", ""))
        chunks.append(item.get("content", ""))
    return "\n".join(chunks)


def _fallback_roster_from_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    athletes: list[dict[str, Any]] = []
    for row in rows:
        values = list(row.values())
        if not values:
            continue
        name = row.get("name") or row.get("athlete") or row.get("col_1") or ""
        if not name or len(name.split()) < 2:
            continue
        athletes.append(
            {
                "name": name,
                "weight_class": row.get("weight") or row.get("weight class") or row.get("col_2"),
                "class_year": row.get("year") or row.get("class") or row.get("col_3"),
                "hometown": row.get("hometown") or row.get("home town") or row.get("col_4"),
                "email": row.get("email") or "",
            }
        )
    return athletes


def _fallback_events_from_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        values = list(row.values())
        if not values:
            continue
        opponent = row.get("opponent") or row.get("match") or row.get("col_2") or row.get("col_1") or ""
        date_val = row.get("date") or row.get("event date") or row.get("col_1") or ""
        location = row.get("location") or row.get("site") or row.get("col_3") or ""
        venue = row.get("venue") or row.get("col_4") or ""
        normalized = " ".join(values).lower()
        is_away = (" at " in f" {normalized} ") or ("away" in normalized) or ("@" in normalized)
        if not opponent:
            continue
        events.append(
            {
                "opponent": opponent,
                "event_date": date_val,
                "location": location,
                "venue": venue,
                "is_away": is_away,
            }
        )
    return events


def _extract_with_openai(kind: str, url: str, raw_text: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.openai_api_key:
        return []

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "You extract Cornell wrestling operations data from messy webpages. "
        "Return compact valid JSON only."
    )
    if kind == "roster":
        instruction = (
            "Extract an object with key 'athletes' containing an array of athlete objects. "
            "Fields: name, weight_class, class_year, hometown, email. "
            "Leave missing fields as empty strings."
        )
        key = "athletes"
    else:
        instruction = (
            "Extract an object with key 'events' containing an array of event objects. "
            "Fields: opponent, event_date, location, venue, is_away(boolean)."
        )
        key = "events"

    seed_rows = json.dumps(rows[:60], ensure_ascii=True)
    prompt = (
        f"Source URL: {url}\n\n"
        f"Candidate table rows:\n{seed_rows}\n\n"
        f"Page text excerpt:\n{raw_text[:15000]}\n\n"
        f"{instruction}"
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    data = parsed.get(key)
    if isinstance(data, list):
        return data
    return []


def import_roster_from_url(url: str) -> list[dict[str, Any]]:
    html = ""
    try:
        html = _fetch_url(url)
    except Exception:
        html = ""

    if not html:
        html = _tavily_fallback(url)

    rows = _extract_table_rows(html)
    raw_text = _html_to_text(html)

    athletes = _extract_with_openai("roster", url, raw_text, rows)
    if athletes:
        return athletes
    return _fallback_roster_from_rows(rows)


def import_schedule_from_url(url: str) -> list[dict[str, Any]]:
    html = ""
    try:
        html = _fetch_url(url)
    except Exception:
        html = ""

    if not html:
        html = _tavily_fallback(url)

    rows = _extract_table_rows(html)
    raw_text = _html_to_text(html)

    events = _extract_with_openai("schedule", url, raw_text, rows)
    if events:
        return events

    parsed = _fallback_events_from_rows(rows)
    if parsed:
        return parsed

    # Last-resort extraction from text lines if no table exists.
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    events = []
    date_pattern = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?\s+\d{1,2}", re.I)
    for idx, line in enumerate(lines):
        if not date_pattern.search(line):
            continue
        opponent = lines[idx + 1] if idx + 1 < len(lines) else "TBD Opponent"
        location = lines[idx + 2] if idx + 2 < len(lines) else ""
        is_away = (" at " in line.lower()) or ("@" in line) or ("away" in line.lower())
        events.append(
            {
                "opponent": opponent,
                "event_date": line,
                "location": location,
                "venue": "",
                "is_away": is_away,
            }
        )
    return events
