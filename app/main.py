from __future__ import annotations

from urllib.parse import quote_plus

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.db import (
    assign_recruit,
    create_recruit,
    create_travel_plan,
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
    list_recruits,
    list_travel_plans,
)
from app.services.link_importer import import_roster_from_url, import_schedule_from_url
from app.services.notifications import render_assignment_message
from app.services.ramp_client import RampClient
from app.services.travel_planner import suggest_hotel

app = FastAPI(title="Cornell Wrestling Ramp-Style Ops Demo")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ramp_client = RampClient()


def _dollars_to_cents(value: str) -> int:
    try:
        return max(0, int(float(value) * 100))
    except Exception:
        return 0


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def index(request: Request, msg: str = "", err: str = ""):
    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "msg": msg,
            "err": err,
            "athletes": list_athletes(),
            "events": list_events(),
            "away_events": list_away_events(),
            "travel_plans": list_travel_plans(),
            "recruits": list_recruits(),
            "assignments": list_recruit_assignments(),
            "ramp_live": ramp_client.is_live,
            "openai_set": bool(settings.openai_api_key),
            "tavily_set": bool(settings.tavily_api_key),
        },
    )


@app.post("/import/links")
def import_links(
    roster_url: str = Form(default=""),
    schedule_url: str = Form(default=""),
):
    try:
        created_athletes = 0
        created_events = 0
        if roster_url.strip():
            athletes = import_roster_from_url(roster_url.strip())
            created_athletes = insert_athletes(athletes, roster_url.strip())
        if schedule_url.strip():
            events = import_schedule_from_url(schedule_url.strip())
            created_events = insert_events(events, schedule_url.strip())

        msg = quote_plus(
            f"Imported {created_athletes} athletes and {created_events} schedule events."
        )
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Import failed: {exc}")
        return RedirectResponse(url=f"/?err={err}", status_code=303)


@app.post("/travel/plan/{event_id}")
def plan_travel(
    event_id: int,
    owner_email: str = Form(default="travelops@cornellwrestling.org"),
    spend_limit_dollars: str = Form(default="3500"),
    transport_mode: str = Form(default="charter bus"),
    depart_at: str = Form(default=""),
    return_at: str = Form(default=""),
    notes: str = Form(default=""),
):
    event = get_event(event_id)
    if not event:
        err = quote_plus("Event not found.")
        return RedirectResponse(url=f"/?err={err}", status_code=303)
    if not event["is_away"]:
        err = quote_plus("Travel planning is only enabled for away events.")
        return RedirectResponse(url=f"/?err={err}", status_code=303)

    try:
        hotel_name, hotel_address = suggest_hotel(event["location"] or "", event["venue"] or "")
        card = ramp_client.create_travel_card(
            event_title=f"{event['opponent']} ({event['event_date'] or 'TBD'})",
            spend_limit_cents=_dollars_to_cents(spend_limit_dollars),
            owner_email=owner_email,
        )
        create_travel_plan(
            event_id=event_id,
            hotel_name=hotel_name,
            hotel_address=hotel_address,
            transport_mode=transport_mode,
            depart_at=depart_at,
            return_at=return_at,
            notes=notes,
            ramp_card_id=card.card_id,
            ramp_card_last4=card.last4,
            ramp_wallet_link=card.wallet_link,
        )
        msg = quote_plus(
            f"Travel plan created for {event['opponent']}. Card {card.card_id} (****{card.last4}) ready."
        )
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Travel planning failed: {exc}")
        return RedirectResponse(url=f"/?err={err}", status_code=303)


@app.post("/recruits")
def add_recruit(
    name: str = Form(...),
    grad_year: str = Form(default=""),
    weight_class: str = Form(default=""),
    home_town: str = Form(default=""),
    guardian_email: str = Form(default=""),
    source_url: str = Form(default="manual"),
):
    try:
        create_recruit(
            name=name,
            grad_year=grad_year,
            weight_class=weight_class,
            home_town=home_town,
            guardian_email=guardian_email,
            source_url=source_url,
        )
        msg = quote_plus(f"Recruit {name} created.")
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Recruit creation failed: {exc}")
        return RedirectResponse(url=f"/?err={err}", status_code=303)


@app.post("/recruits/{recruit_id}/assign")
def assign_recruit_to_athlete(
    recruit_id: int,
    athlete_id: int = Form(...),
    assigned_by: str = Form(default="Head Coach"),
    owner_email: str = Form(default="recruiting@cornellwrestling.org"),
    spend_limit_dollars: str = Form(default="300"),
):
    recruit = get_recruit(recruit_id)
    athlete = get_athlete(athlete_id)
    if not recruit or not athlete:
        err = quote_plus("Recruit or athlete not found.")
        return RedirectResponse(url=f"/?err={err}", status_code=303)

    try:
        card = ramp_client.create_recruiting_card(
            recruit_name=recruit["name"],
            assigned_athlete_name=athlete["name"],
            spend_limit_cents=_dollars_to_cents(spend_limit_dollars),
            owner_email=owner_email,
        )
        assign_recruit(
            recruit_id=recruit_id,
            athlete_id=athlete_id,
            assigned_by=assigned_by,
            spend_limit_cents=_dollars_to_cents(spend_limit_dollars),
            ramp_card_id=card.card_id,
            wallet_link=card.wallet_link,
            apple_wallet_link=card.apple_wallet_link,
        )
        message = render_assignment_message(
            recruit_name=recruit["name"],
            athlete_name=athlete["name"],
            wallet_link=card.wallet_link,
            apple_wallet_link=card.apple_wallet_link,
        )
        msg = quote_plus(message)
        return RedirectResponse(url=f"/?msg={msg}", status_code=303)
    except Exception as exc:
        err = quote_plus(f"Recruit assignment failed: {exc}")
        return RedirectResponse(url=f"/?err={err}", status_code=303)


@app.get("/wallet/card/{card_id}")
def wallet_card(request: Request, card_id: str):
    wallet_link = f"https://demo.cornellwrestling.local/cards/{card_id}"
    apple_wallet_link = f"https://wallet.apple.com/pass?url={quote_plus(wallet_link)}"
    return templates.TemplateResponse(
        request=request,
        name="wallet_card.html",
        context={
            "card_id": card_id,
            "wallet_link": wallet_link,
            "apple_wallet_link": apple_wallet_link,
        },
    )
