from __future__ import annotations

import json
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import get_settings
from app.db import (
    assign_recruit,
    create_recruit,
    create_recruit_visit,
    create_travel_card_entry,
    create_travel_plan,
    create_visit_host_card,
    find_athletes_by_state,
    get_athlete,
    get_event,
    get_recruit,
    init_db,
    insert_athletes,
    insert_events,
    list_athletes,
    list_away_events,
    list_events,
    list_recruit_assignments,
    list_recruit_visits,
    list_recruits,
    list_sports,
    list_starters,
    list_travel_cards_for_plan,
    list_travel_plans,
    list_visit_host_cards,
    parse_state,
    toggle_starter,
    update_athlete_email,
)
from app.services.link_importer import import_roster_from_url, import_schedule_from_url
from app.services.notifications import render_assignment_message
from app.services.ramp_client import RampClient
from app.services.recruit_chat import extract_recruit
from app.services.travel_chat import chat_plan, search_hotels
from app.services.travel_planner import suggest_hotel

app = FastAPI(title="Cornell Athletics")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ramp_client = RampClient()


def _dollars_to_cents(value: str) -> int:
    try:
        return max(0, int(float(value) * 100))
    except Exception:
        return 0


def _base_context(sport: str) -> dict:
    settings = get_settings()
    return {
        "sports": list_sports(),
        "selected_sport": sport,
        "perplexity_set": bool(settings.perplexity_api_key),
    }


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def index():
    return RedirectResponse(url="/roster", status_code=302)


# ── Roster ──────────────────────────────────────────────

@app.get("/roster")
def roster_view(request: Request, msg: str = "", err: str = "", sport: str = ""):
    ctx = _base_context(sport)
    ctx.update({
        "msg": msg, "err": err, "active_tab": "roster",
        "athletes": list_athletes(sport),
        "starters": list_starters(sport),
    })
    return templates.TemplateResponse(request=request, name="roster.html", context=ctx)


# ── Travel Planning ─────────────────────────────────────

@app.get("/travel")
def travel_view(request: Request, msg: str = "", err: str = "", sport: str = "", event_id: int = 0):
    ctx = _base_context(sport)
    away_events = list_away_events(sport)
    starters = list_starters(sport)

    selected_event = None
    if event_id:
        selected_event = get_event(event_id)

    plans = list_travel_plans()
    plans_with_cards = []
    for plan in plans:
        cards = list_travel_cards_for_plan(plan["id"])
        plans_with_cards.append({"plan": plan, "cards": cards})

    ctx.update({
        "msg": msg, "err": err, "active_tab": "travel",
        "starters": starters,
        "athletes": list_athletes(sport),
        "away_events": away_events,
        "selected_event": selected_event,
        "selected_event_id": event_id,
        "travel_plans": plans_with_cards,
    })
    return templates.TemplateResponse(request=request, name="travel.html", context=ctx)


class ChatRequest(BaseModel):
    message: str
    event_context: str


@app.post("/api/travel/chat")
def travel_chat_api(req: ChatRequest):
    try:
        result = chat_plan(req.message, req.event_context)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


class HotelSearchRequest(BaseModel):
    location: str
    dates: str
    preferences: str = ""


@app.post("/api/travel/hotels")
def travel_hotels_api(req: HotelSearchRequest):
    try:
        hotels = search_hotels(req.location, req.dates, req.preferences)
        return JSONResponse(hotels)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/travel/plan/{event_id}")
def plan_travel(
    event_id: int,
    sport: str = "",
    owner_email: str = Form(default="travelops@cornellwrestling.org"),
    spend_limit_dollars: str = Form(default="3500"),
    transport_mode: str = Form(default="charter bus"),
    depart_at: str = Form(default=""),
    return_at: str = Form(default=""),
    notes: str = Form(default=""),
    hotel_name: str = Form(default=""),
    hotel_address: str = Form(default=""),
    athlete_ids: str = Form(default=""),
):
    base = f"/travel?sport={quote_plus(sport)}" if sport else "/travel"
    event = get_event(event_id)
    if not event:
        return RedirectResponse(url=f"{base}&err={quote_plus('Event not found.')}", status_code=303)

    try:
        if not hotel_name:
            hotel_name, hotel_address = suggest_hotel(event["location"] or "", event["venue"] or "")

        # Parse athlete IDs from the travel party
        ids = [int(x) for x in athlete_ids.split(",") if x.strip()]
        total_cents = _dollars_to_cents(spend_limit_dollars)
        per_person_cents = total_cents // max(len(ids), 1)

        # Create one card per athlete
        cards = []
        for aid in ids:
            athlete = get_athlete(aid)
            athlete_name = athlete["name"] if athlete else f"Athlete #{aid}"
            card = ramp_client.create_travel_card(
                event_title=f"{event['opponent']} ({event['event_date'] or 'TBD'}) - {athlete_name}",
                spend_limit_cents=per_person_cents,
                owner_email=owner_email,
            )
            cards.append((aid, card))

        # Use first card as the plan-level card (backward compat)
        plan_card = cards[0][1] if cards else ramp_client.create_travel_card(
            event_title=f"{event['opponent']} ({event['event_date'] or 'TBD'})",
            spend_limit_cents=total_cents,
            owner_email=owner_email,
        )

        plan_id = create_travel_plan(
            event_id=event_id, hotel_name=hotel_name, hotel_address=hotel_address,
            transport_mode=transport_mode, depart_at=depart_at, return_at=return_at,
            notes=notes, ramp_card_id=plan_card.card_id, ramp_card_last4=plan_card.last4,
            ramp_wallet_link=plan_card.wallet_link,
        )

        # Store individual athlete cards
        for aid, card in cards:
            create_travel_card_entry(
                travel_plan_id=plan_id, athlete_id=aid,
                ramp_card_id=card.card_id, ramp_card_last4=card.last4,
                wallet_link=card.wallet_link, spend_limit_cents=per_person_cents,
            )

        msg = quote_plus(f"Travel plan created for {event['opponent']}. {len(cards)} Ramp cards issued.")
        return RedirectResponse(url=f"{base}&msg={msg}" if sport else f"{base}?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Travel planning failed: {exc}")
        return RedirectResponse(url=f"{base}&err={err}" if sport else f"{base}?err={err}", status_code=303)


# ── Recruiting ──────────────────────────────────────────

@app.get("/recruiting")
def recruiting_view(request: Request, msg: str = "", err: str = "", sport: str = ""):
    ctx = _base_context(sport)
    ctx.update({
        "msg": msg, "err": err, "active_tab": "recruiting",
        "athletes": list_athletes(sport),
        "recruits": list_recruits(),
        "assignments": list_recruit_assignments(),
    })
    return templates.TemplateResponse(request=request, name="recruiting.html", context=ctx)


@app.post("/recruits")
def add_recruit(
    sport: str = "",
    name: str = Form(...),
    grad_year: str = Form(default=""),
    weight_class: str = Form(default=""),
    home_town: str = Form(default=""),
    guardian_email: str = Form(default=""),
    source_url: str = Form(default="manual"),
):
    base = f"/recruiting?sport={quote_plus(sport)}" if sport else "/recruiting"
    try:
        create_recruit(name=name, grad_year=grad_year, weight_class=weight_class,
                       home_town=home_town, guardian_email=guardian_email, source_url=source_url)
        msg = quote_plus(f"Recruit {name} created.")
        return RedirectResponse(url=f"{base}&msg={msg}" if sport else f"{base}?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Recruit creation failed: {exc}")
        return RedirectResponse(url=f"{base}&err={err}" if sport else f"{base}?err={err}", status_code=303)


@app.post("/recruits/{recruit_id}/assign")
def assign_recruit_to_athlete(
    recruit_id: int,
    sport: str = "",
    athlete_id: int = Form(...),
    assigned_by: str = Form(default="Head Coach"),
    owner_email: str = Form(default="recruiting@cornellwrestling.org"),
    spend_limit_dollars: str = Form(default="300"),
):
    base = f"/recruiting?sport={quote_plus(sport)}" if sport else "/recruiting"
    recruit = get_recruit(recruit_id)
    athlete = get_athlete(athlete_id)
    if not recruit or not athlete:
        return RedirectResponse(url=f"{base}&err={quote_plus('Recruit or athlete not found.')}" if sport else f"{base}?err={quote_plus('Recruit or athlete not found.')}", status_code=303)

    try:
        card = ramp_client.create_recruiting_card(
            recruit_name=recruit["name"], assigned_athlete_name=athlete["name"],
            spend_limit_cents=_dollars_to_cents(spend_limit_dollars), owner_email=owner_email,
        )
        assign_recruit(
            recruit_id=recruit_id, athlete_id=athlete_id, assigned_by=assigned_by,
            spend_limit_cents=_dollars_to_cents(spend_limit_dollars),
            ramp_card_id=card.card_id, wallet_link=card.wallet_link, apple_wallet_link=card.apple_wallet_link,
        )
        message = render_assignment_message(
            recruit_name=recruit["name"], athlete_name=athlete["name"],
            wallet_link=card.wallet_link, apple_wallet_link=card.apple_wallet_link,
        )
        msg = quote_plus(message)
        return RedirectResponse(url=f"{base}&msg={msg}" if sport else f"{base}?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Recruit assignment failed: {exc}")
        return RedirectResponse(url=f"{base}&err={err}" if sport else f"{base}?err={err}", status_code=303)


# ── Recruit Chat API ────────────────────────────────────

class RecruitChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []
    sport: str = ""


@app.post("/api/recruiting/chat")
def recruit_chat_api(req: RecruitChatRequest):
    try:
        result = extract_recruit(req.message, req.conversation_history, req.sport)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


class RecruitConfirmRequest(BaseModel):
    name: str
    grad_year: str = ""
    weight_class: str = ""
    home_town: str = ""
    guardian_email: str = ""
    source_url: str = "chat"
    sport: str = ""


@app.post("/api/recruiting/confirm")
def recruit_confirm_api(req: RecruitConfirmRequest):
    try:
        rid = create_recruit(
            name=req.name, grad_year=req.grad_year, weight_class=req.weight_class,
            home_town=req.home_town, guardian_email=req.guardian_email, source_url=req.source_url,
        )
        return JSONResponse({"ok": True, "id": rid, "name": req.name})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ── Recruit Visits ─────────────────────────────────────

@app.get("/recruiting/visits")
def recruit_visits_view(request: Request, msg: str = "", err: str = "", sport: str = ""):
    ctx = _base_context(sport)
    visits = list_recruit_visits()
    visits_with_cards = []
    for v in visits:
        cards = list_visit_host_cards(v["id"])
        visits_with_cards.append({"visit": v, "cards": cards})
    ctx.update({
        "msg": msg, "err": err, "active_tab": "visits",
        "recruits": list_recruits(),
        "visits": visits_with_cards,
    })
    return templates.TemplateResponse(request=request, name="recruit_visits.html", context=ctx)


@app.get("/api/recruiting/visits/preview")
def visit_preview_api(recruit_id: int, sport: str = ""):
    recruit = get_recruit(recruit_id)
    if not recruit:
        return JSONResponse({"error": "Recruit not found"}, status_code=404)
    state = parse_state(recruit["home_town"] or "")
    if not state:
        return JSONResponse({"state": None, "athletes": [], "message": "Could not determine state from recruit's hometown."})
    athletes = find_athletes_by_state(state, sport)
    return JSONResponse({
        "state": state,
        "recruit_hometown": recruit["home_town"],
        "athletes": [{"id": a["id"], "name": a["name"], "hometown": a["hometown"], "sport": a["sport"]} for a in athletes],
    })


@app.post("/recruiting/visits")
def create_visit(
    sport: str = "",
    recruit_id: int = Form(...),
    visit_date: str = Form(default=""),
    spend_limit_dollars: str = Form(default="300"),
    athlete_ids: str = Form(default=""),
    notes: str = Form(default=""),
    owner_email: str = Form(default="recruiting@cornellwrestling.org"),
):
    base = f"/recruiting/visits?sport={quote_plus(sport)}" if sport else "/recruiting/visits"
    recruit = get_recruit(recruit_id)
    if not recruit:
        return RedirectResponse(url=f"{base}&err={quote_plus('Recruit not found.')}" if sport else f"{base}?err={quote_plus('Recruit not found.')}", status_code=303)

    try:
        per_person_cents = _dollars_to_cents(spend_limit_dollars)
        visit_id = create_recruit_visit(
            recruit_id=recruit_id, visit_date=visit_date,
            spend_limit_cents=per_person_cents, notes=notes,
        )

        ids = [int(x) for x in athlete_ids.split(",") if x.strip()]
        card_count = 0
        for aid in ids:
            athlete = get_athlete(aid)
            if not athlete:
                continue
            card = ramp_client.create_recruiting_card(
                recruit_name=recruit["name"], assigned_athlete_name=athlete["name"],
                spend_limit_cents=per_person_cents, owner_email=owner_email,
            )
            create_visit_host_card(
                visit_id=visit_id, athlete_id=aid,
                ramp_card_id=card.card_id, ramp_card_last4=card.last4,
                wallet_link=card.wallet_link, apple_wallet_link=card.apple_wallet_link,
                spend_limit_cents=per_person_cents,
            )
            card_count += 1

        msg = quote_plus(f"Visit planned for {recruit['name']}. {card_count} host cards issued.")
        return RedirectResponse(url=f"{base}&msg={msg}" if sport else f"{base}?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Visit creation failed: {exc}")
        return RedirectResponse(url=f"{base}&err={err}" if sport else f"{base}?err={err}", status_code=303)


# ── API endpoints ───────────────────────────────────────

@app.patch("/athletes/{athlete_id}/starter")
def patch_athlete_starter(athlete_id: int):
    try:
        is_starter = toggle_starter(athlete_id)
        return JSONResponse({"ok": True, "is_starter": is_starter})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.patch("/athletes/{athlete_id}/email")
def patch_athlete_email(athlete_id: int, email: str = Form(default="")):
    try:
        update_athlete_email(athlete_id, email.strip())
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@app.get("/wallet/card/{card_id}")
def wallet_card(request: Request, card_id: str):
    wallet_link = f"https://demo.cornellwrestling.local/cards/{card_id}"
    apple_wallet_link = f"https://wallet.apple.com/pass?url={quote_plus(wallet_link)}"
    return templates.TemplateResponse(
        request=request, name="wallet_card.html",
        context={"card_id": card_id, "wallet_link": wallet_link, "apple_wallet_link": apple_wallet_link,
                 "selected_sport": "", "active_tab": ""},
    )
