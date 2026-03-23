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
                sport TEXT,
                is_starter INTEGER NOT NULL DEFAULT 0,
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
                sport TEXT,
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

            CREATE TABLE IF NOT EXISTS travel_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                travel_plan_id INTEGER NOT NULL,
                athlete_id INTEGER NOT NULL,
                ramp_card_id TEXT,
                ramp_card_last4 TEXT,
                wallet_link TEXT,
                spend_limit_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(travel_plan_id) REFERENCES travel_plans(id),
                FOREIGN KEY(athlete_id) REFERENCES athletes(id)
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

            CREATE TABLE IF NOT EXISTS recruit_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recruit_id INTEGER NOT NULL,
                visit_date TEXT,
                status TEXT NOT NULL DEFAULT 'planned',
                spend_limit_cents INTEGER NOT NULL DEFAULT 30000,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(recruit_id) REFERENCES recruits(id)
            );

            CREATE TABLE IF NOT EXISTS visit_host_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visit_id INTEGER NOT NULL,
                athlete_id INTEGER NOT NULL,
                ramp_card_id TEXT,
                ramp_card_last4 TEXT,
                wallet_link TEXT,
                apple_wallet_link TEXT,
                spend_limit_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(visit_id) REFERENCES recruit_visits(id),
                FOREIGN KEY(athlete_id) REFERENCES athletes(id)
            );
            """
        )


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def insert_athletes(athletes: Iterable[dict], source_url: str, sport: str = "") -> int:
    created = 0
    with get_conn() as conn:
        for athlete in athletes:
            if not athlete.get("name"):
                continue
            conn.execute(
                """
                INSERT INTO athletes(name, weight_class, class_year, hometown, email, sport, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    athlete.get("name"),
                    athlete.get("weight_class"),
                    athlete.get("class_year"),
                    athlete.get("hometown"),
                    athlete.get("email"),
                    sport,
                    source_url,
                    now_iso(),
                ),
            )
            created += 1
    return created


def insert_events(events: Iterable[dict], source_url: str, sport: str = "") -> int:
    created = 0
    with get_conn() as conn:
        for event in events:
            if not event.get("opponent"):
                continue
            is_away = bool(event.get("is_away"))
            conn.execute(
                """
                INSERT INTO events(opponent, event_date, location, venue, is_away, sport, source_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.get("opponent"),
                    event.get("event_date"),
                    event.get("location"),
                    event.get("venue"),
                    1 if is_away else 0,
                    sport,
                    source_url,
                    now_iso(),
                ),
            )
            created += 1
    return created


def clear_all_athletes_and_events() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM athletes")
        conn.execute("DELETE FROM events")


def list_sports() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT sport FROM athletes WHERE sport != '' "
            "UNION SELECT DISTINCT sport FROM events WHERE sport != '' "
            "ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]


def list_athletes(sport: str = "") -> list[sqlite3.Row]:
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM athletes WHERE sport = ? ORDER BY name, id",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM athletes ORDER BY sport, name, id"
            ).fetchall()
    return rows


def list_events(sport: str = "") -> list[sqlite3.Row]:
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM events WHERE sport = ? ORDER BY event_date, id",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY sport, event_date, id"
            ).fetchall()
    return rows


def list_away_events(sport: str = "") -> list[sqlite3.Row]:
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM events WHERE is_away = 1 AND sport = ? ORDER BY event_date, id",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE is_away = 1 ORDER BY sport, event_date, id"
            ).fetchall()
    return rows


def update_athlete_email(athlete_id: int, email: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE athletes SET email = ? WHERE id = ?", (email, athlete_id))


def toggle_starter(athlete_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT is_starter FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
        if not row:
            return False
        new_val = 0 if row["is_starter"] else 1
        conn.execute("UPDATE athletes SET is_starter = ? WHERE id = ?", (new_val, athlete_id))
        return bool(new_val)


def list_starters(sport: str = "") -> list[sqlite3.Row]:
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM athletes WHERE is_starter = 1 AND sport = ? ORDER BY name, id",
                (sport,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM athletes WHERE is_starter = 1 ORDER BY sport, name, id"
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


def create_travel_card_entry(
    *,
    travel_plan_id: int,
    athlete_id: int,
    ramp_card_id: str,
    ramp_card_last4: str,
    wallet_link: str,
    spend_limit_cents: int,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO travel_cards(travel_plan_id, athlete_id, ramp_card_id, ramp_card_last4, wallet_link, spend_limit_cents, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (travel_plan_id, athlete_id, ramp_card_id, ramp_card_last4, wallet_link, spend_limit_cents, now_iso()),
        )
        return int(cur.lastrowid)


def list_travel_cards_for_plan(travel_plan_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT tc.*, a.name AS athlete_name
            FROM travel_cards tc
            JOIN athletes a ON a.id = tc.athlete_id
            WHERE tc.travel_plan_id = ?
            ORDER BY a.name, tc.id
            """,
            (travel_plan_id,),
        ).fetchall()
    return rows


# ── Recruit Visits ──────────────────────────────────────

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
_ABBREVS = set(US_STATES.values())


def parse_state(hometown: str) -> str | None:
    if not hometown:
        return None
    parts = hometown.strip().rsplit(",", 1)
    if len(parts) < 2:
        return None
    token = parts[1].strip().rstrip(".")
    upper = token.upper()[:2]
    if upper in _ABBREVS:
        return upper
    full = token.lower()
    if full in US_STATES:
        return US_STATES[full]
    return None


def find_athletes_by_state(state: str, sport: str = "") -> list[sqlite3.Row]:
    with get_conn() as conn:
        if sport:
            rows = conn.execute(
                "SELECT * FROM athletes WHERE hometown LIKE ? AND sport = ? ORDER BY name",
                (f"%, {state}%", sport),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM athletes WHERE hometown LIKE ? ORDER BY name",
                (f"%, {state}%",),
            ).fetchall()
    return rows


def create_recruit_visit(
    *,
    recruit_id: int,
    visit_date: str,
    spend_limit_cents: int,
    notes: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO recruit_visits(recruit_id, visit_date, status, spend_limit_cents, notes, created_at)
            VALUES (?, ?, 'planned', ?, ?, ?)
            """,
            (recruit_id, visit_date, spend_limit_cents, notes, now_iso()),
        )
        return int(cur.lastrowid)


def list_recruit_visits() -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT rv.*, r.name AS recruit_name, r.home_town AS recruit_hometown
            FROM recruit_visits rv
            JOIN recruits r ON r.id = rv.recruit_id
            ORDER BY rv.created_at DESC, rv.id DESC
            """
        ).fetchall()
    return rows


def get_recruit_visit(visit_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM recruit_visits WHERE id = ?", (visit_id,)
        ).fetchone()


def create_visit_host_card(
    *,
    visit_id: int,
    athlete_id: int,
    ramp_card_id: str,
    ramp_card_last4: str,
    wallet_link: str,
    apple_wallet_link: str,
    spend_limit_cents: int,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO visit_host_cards(
                visit_id, athlete_id, ramp_card_id, ramp_card_last4,
                wallet_link, apple_wallet_link, spend_limit_cents, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (visit_id, athlete_id, ramp_card_id, ramp_card_last4,
             wallet_link, apple_wallet_link, spend_limit_cents, now_iso()),
        )
        return int(cur.lastrowid)


def list_visit_host_cards(visit_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT vhc.*, a.name AS athlete_name, a.hometown AS athlete_hometown
            FROM visit_host_cards vhc
            JOIN athletes a ON a.id = vhc.athlete_id
            WHERE vhc.visit_id = ?
            ORDER BY a.name, vhc.id
            """,
            (visit_id,),
        ).fetchall()
    return rows
