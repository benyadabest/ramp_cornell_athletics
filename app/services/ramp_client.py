from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.config import get_settings


@dataclass
class RampCard:
    card_id: str
    last4: str
    wallet_link: str
    apple_wallet_link: str


class RampClient:
    """Thin Ramp API wrapper with a local demo fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        return bool(self.settings.ramp_client_id and self.settings.ramp_client_secret)

    def _demo_card(self, label: str) -> RampCard:
        card_id = f"demo_{label}_{secrets.token_hex(6)}"
        last4 = str(secrets.randbelow(9000) + 1000)
        wallet_link = f"https://demo.cornellwrestling.local/cards/{card_id}"
        apple_wallet_link = f"https://wallet.apple.com/pass?url={quote_plus(wallet_link)}"
        return RampCard(
            card_id=card_id,
            last4=last4,
            wallet_link=wallet_link,
            apple_wallet_link=apple_wallet_link,
        )

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _get_access_token(self) -> str:
        if self._token and self._token_expires_at and datetime.now(tz=timezone.utc) < self._token_expires_at:
            return self._token

        auth_blob = f"{self.settings.ramp_client_id}:{self.settings.ramp_client_secret}"
        encoded = base64.b64encode(auth_blob.encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        with httpx.Client(timeout=20) as client:
            response = client.post(self.settings.ramp_token_url, headers=headers, data=data)
            response.raise_for_status()
            payload = response.json()

        self._token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in - 60)
        return self._token

    def create_travel_card(
        self,
        *,
        event_title: str,
        spend_limit_cents: int,
        owner_email: str,
    ) -> RampCard:
        if not self.is_live:
            return self._demo_card("travel")

        payload: dict[str, Any] = {
            "purpose": f"Cornell Wrestling Travel - {event_title}",
            "spend_limit_cents": spend_limit_cents,
            "owner_email": owner_email,
            "type": "virtual",
        }
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.settings.ramp_api_base_url}/cards/virtual",
                headers=self._auth_headers(),
                json=payload,
            )
            response.raise_for_status()
            card = response.json()

        wallet_link = card.get("wallet_link") or card.get("provisioning_url") or ""
        apple_wallet_link = (
            f"https://wallet.apple.com/pass?url={quote_plus(wallet_link)}" if wallet_link else ""
        )
        return RampCard(
            card_id=str(card["id"]),
            last4=str(card.get("last4", "0000")),
            wallet_link=wallet_link,
            apple_wallet_link=apple_wallet_link,
        )

    def create_recruiting_card(
        self,
        *,
        recruit_name: str,
        assigned_athlete_name: str,
        spend_limit_cents: int,
        owner_email: str,
    ) -> RampCard:
        if not self.is_live:
            return self._demo_card("recruit")

        payload: dict[str, Any] = {
            "purpose": f"Recruit Hosting - {recruit_name} / {assigned_athlete_name}",
            "spend_limit_cents": spend_limit_cents,
            "owner_email": owner_email,
            "type": "virtual",
        }
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.settings.ramp_api_base_url}/cards/virtual",
                headers=self._auth_headers(),
                json=payload,
            )
            response.raise_for_status()
            card = response.json()

        wallet_link = card.get("wallet_link") or card.get("provisioning_url") or ""
        apple_wallet_link = (
            f"https://wallet.apple.com/pass?url={quote_plus(wallet_link)}" if wallet_link else ""
        )
        return RampCard(
            card_id=str(card["id"]),
            last4=str(card.get("last4", "0000")),
            wallet_link=wallet_link,
            apple_wallet_link=apple_wallet_link,
        )
