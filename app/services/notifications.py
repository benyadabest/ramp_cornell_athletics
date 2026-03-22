from __future__ import annotations

from app.config import get_settings


def get_default_notification_targets() -> list[str]:
    settings = get_settings()
    raw = settings.default_recruiting_staff_emails.strip()
    if not raw:
        return []
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def render_assignment_message(
    *,
    recruit_name: str,
    athlete_name: str,
    wallet_link: str,
    apple_wallet_link: str,
) -> str:
    return (
        f"Recruit '{recruit_name}' was assigned to athlete '{athlete_name}'. "
        f"Ramp card link: {wallet_link} | Apple Wallet: {apple_wallet_link}"
    )
