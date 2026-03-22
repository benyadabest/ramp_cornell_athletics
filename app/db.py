from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import get_settings


def _db_path() -> str:
    settings = get_settings()
    return str(Path(settings.database_path).resolve())


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS athletes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                weight_class TEXT,
                class_year TEXT,
                hometown TEXT,
                email TEXT,
                source_url TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opponent TEXT NOT NULL,
                event_date TEXT,
                location TEXT,
                venue TEXT,
                is_away INTEGER NOT NULL DEFAULT 0,
                source_url TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS travel_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                hotel_name TEXT,
                hotel_address TEXT,
                transport_mode TEXT,
                depart_at TEXT,
                return_at TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                ramp_card_id TEXT,
                ramp_card_last4 TEXT,
                ramp_wallet_link TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS recruits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                grad_year TEXT,
                weight_class TEXT,
                home_town TEXT,
                guardian_email TEXT,
                source_url TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recruit_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recruit_id INTEGER NOT NULL,
                athlete_id INTEGER NOT NULL,
                assigned_by TEXT,
                assigned_at TEXT NOT NULL,
                spend_limit_cents INTEGER NOT NULL,
                ramp_card_id TEXT,
                wallet_link TEXT,
                apple_wallet_link TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY(recruit_id) REFERENCES recruits(id),
                FOREIGN KEY(athlete_id) REFERENCES athletes(id)
            );
            """
        )


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def insert_athletes(athletes: Iterable[dict], source_url: str) -> int:
    created = 0
    with get_conn() as conn:
        for athlete in athletes:
            if not athlete.get("name"):
                continue
            conn.execute(
                """
                INSERT INTO athletes(name, weight_class, class_year, hometown, email, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    athlete.get("name"),
                    athlete.get("weight_class"),
                    athlete.get("class_year"),
                    athlete.get("hometown"),
                    athlete.get("email"),
                    source_url,
                    now_iso(),
                ),
            )
            created += 1
    return created


def insert_events(events: Iterable[dict], source_url: str) -> int:
    created = 0
    with get_conn() as conn:
        for event in events:
            if not event.get("opponent"):
                continue
            is_away = bool(event.get("is_away"))
            conn.execute(
                """
                INSERT INTO events(opponent, event_date, location, venue, is_away, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("opponent"),
                    event.get("event_date"),
                    event.get("location"),
                    event.get("venue"),
                    1 if is_away else 0,
                    source_url,
                    now_iso(),
                ),
            )
            created += 1
    return created


def list_athletes() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM athletes ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return rows


def list_events() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return rows


def list_away_events() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE is_away = 1 ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return rows


def get_event(event_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return row


def create_travel_plan(
    *,
    event_id: int,
    hotel_name: str,
    hotel_address: str,
    transport_mode: str,
    depart_at: str,
    return_at: str,
    notes: str,
    ramp_card_id: str,
    ramp_card_last4: str,
    ramp_wallet_link: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO travel_plans(
                event_id, hotel_name, hotel_address, transport_mode, depart_at, return_at,
                status, ramp_card_id, ramp_card_last4, ramp_wallet_link, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'provisioned', ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                hotel_name,
                hotel_address,
                transport_mode,
                depart_at,
                return_at,
                ramp_card_id,
                ramp_card_last4,
                ramp_wallet_link,
                notes,
                now_iso(),
            ),
        )
        return int(cur.lastrowid)


def list_travel_plans() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT tp.*, e.opponent, e.event_date, e.location, e.venue
            FROM travel_plans tp
            JOIN events e ON e.id = tp.event_id
            ORDER BY tp.created_at DESC, tp.id DESC
            """
        ).fetchall()
    return rows


def create_recruit(
    *,
    name: str,
    grad_year: str,
    weight_class: str,
    home_town: str,
    guardian_email: str,
    source_url: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO recruits(name, grad_year, weight_class, home_town, guardian_email, source_url, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (name, grad_year, weight_class, home_town, guardian_email, source_url, now_iso()),
        )
        return int(cur.lastrowid)


def list_recruits() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recruits ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return rows


def get_recruit(recruit_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM recruits WHERE id = ?", (recruit_id,)
        ).fetchone()
    return row


def get_athlete(athlete_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM athletes WHERE id = ?", (athlete_id,)
        ).fetchone()
    return row


def assign_recruit(
    *,
    recruit_id: int,
    athlete_id: int,
    assigned_by: str,
    spend_limit_cents: int,
    ramp_card_id: str,
    wallet_link: str,
    apple_wallet_link: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO recruit_assignments(
                recruit_id, athlete_id, assigned_by, assigned_at,
                spend_limit_cents, ramp_card_id, wallet_link, apple_wallet_link, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                recruit_id,
                athlete_id,
                assigned_by,
                now_iso(),
                spend_limit_cents,
                ramp_card_id,
                wallet_link,
                apple_wallet_link,
            ),
        )
        conn.execute(
            "UPDATE recruits SET status = 'assigned' WHERE id = ?",
            (recruit_id,),
        )
        return int(cur.lastrowid)


def list_recruit_assignments() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT ra.*, r.name AS recruit_name, r.guardian_email, a.name AS athlete_name, a.email AS athlete_email
            FROM recruit_assignments ra
            JOIN recruits r ON r.id = ra.recruit_id
            JOIN athletes a ON a.id = ra.athlete_id
            ORDER BY ra.assigned_at DESC, ra.id DESC
            """
        ).fetchall()
    return rows
