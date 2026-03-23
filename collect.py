#!/usr/bin/env python3
"""Standalone script to collect roster + schedule for all Cornell sports."""
from __future__ import annotations

import sys
import time

from app.config import get_settings
from app.db import clear_all_athletes_and_events, init_db, insert_athletes, insert_events
from app.services.link_importer import import_roster_from_url, import_schedule_from_url

ALL_SPORTS = [
    ("Baseball", "baseball"),
    ("Men's Basketball", "mens-basketball"),
    ("Men's Cross Country", "mens-cross-country"),
    ("Football", "football"),
    ("Men's Golf", "mens-golf"),
    ("Men's Ice Hockey", "mens-ice-hockey"),
    ("Men's Lacrosse", "mens-lacrosse"),
    ("Men's Polo", "mens-polo"),
    ("Men's Rowing - Heavyweight", "rowing"),
    ("Men's Rowing - Lightweight", "mens-rowing"),
    ("Men's Soccer", "mens-soccer"),
    ("Sprint Football", "sprint-football"),
    ("Men's Squash", "mens-squash"),
    ("Men's Swimming & Diving", "mens-swimming-and-diving"),
    ("Men's Tennis", "mens-tennis"),
    ("Men's Track & Field", "mens-track-and-field"),
    ("Wrestling", "wrestling"),
    ("Women's Basketball", "womens-basketball"),
    ("Women's Cross Country", "womens-cross-country"),
    ("Equestrian", "equestrian"),
    ("Fencing", "fencing"),
    ("Field Hockey", "field-hockey"),
    ("Women's Gymnastics", "womens-gymnastics"),
    ("Women's Ice Hockey", "womens-ice-hockey"),
    ("Women's Lacrosse", "womens-lacrosse"),
    ("Women's Polo", "womens-polo"),
    ("Women's Rowing", "womens-rowing"),
    ("Sailing", "womens-sailing"),
    ("Women's Soccer", "womens-soccer"),
    ("Softball", "softball"),
    ("Women's Squash", "womens-squash"),
    ("Women's Swimming & Diving", "womens-swimming-and-diving"),
    ("Women's Tennis", "womens-tennis"),
    ("Women's Track & Field", "womens-track-and-field"),
    ("Volleyball", "womens-volleyball"),
]

BASE_URL = "https://cornellbigred.com/sports"


def main() -> None:
    settings = get_settings()
    print(f"OpenAI key: {'set' if settings.openai_api_key else 'MISSING'}")
    print(f"Tavily key: {'set' if settings.tavily_api_key else 'MISSING'}")
    print()

    init_db()
    clear_all_athletes_and_events()

    total = len(ALL_SPORTS)
    total_athletes = 0
    total_events = 0
    start = time.time()

    for idx, (name, slug) in enumerate(ALL_SPORTS):
        num = idx + 1
        print(f"[{num}/{total}] {name}")

        # Roster
        roster_url = f"{BASE_URL}/{slug}/roster"
        try:
            athletes = import_roster_from_url(roster_url)
            count = insert_athletes(athletes, roster_url, sport=name)
            total_athletes += count
            print(f"  roster: {count} athletes")
        except Exception as exc:
            print(f"  roster FAILED: {exc}")

        # Schedule
        schedule_url = f"{BASE_URL}/{slug}/schedule"
        try:
            events = import_schedule_from_url(schedule_url)
            count = insert_events(events, schedule_url, sport=name)
            total_events += count
            print(f"  schedule: {count} events")
        except Exception as exc:
            print(f"  schedule FAILED: {exc}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — {total_athletes} athletes, {total_events} events")


if __name__ == "__main__":
    main()
