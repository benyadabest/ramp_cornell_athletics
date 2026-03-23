# Cornell Wrestling Ramp-Style Operations Demo

Demo platform for **travel + recruiting operations** modeled after a Ramp-powered workflow.

## What this demo does

### Travel workflow
- Imports your wrestling roster and schedule from links.
- Detects away events.
- Lets staff create travel plans for away events (hotel + transport + notes).
- Provisions a travel card via Ramp API (or demo fallback if Ramp keys are not set).
- Stores card links that staff can open immediately.

### Recruiting workflow
- Creates recruits and tracks statuses.
- Assigns each recruit to a current athlete host.
- Provisions a recruit-hosting spend card via Ramp API.
- Generates a card link and Apple Wallet deep link so hosts can use a card directly (instead of receipts/reimbursement).

## Tech stack
- Python 3.11+
- FastAPI + Jinja templates
- SQLite (local demo DB)
- OpenAI API for webpage-to-structured-data extraction
- Tavily API for web enrichment/fallback retrieval
- Ramp API wrapper with live mode + demo mode

## Quickstart

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment:

```bash
cp .env.example .env
```

3. Add keys/secrets in `.env`:
- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `RAMP_CLIENT_ID`
- `RAMP_CLIENT_SECRET`

Optional defaults are already included for host/port and API URLs.

4. Run app:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Open:

```text
http://localhost:8000
```

## Demo usage flow

1. Paste Cornell roster and schedule URLs into the import form.
2. Review imported athletes and away events.
3. For each away event, click **Create Travel Plan + Ramp Card**.
4. Add recruits.
5. Assign each recruit to an athlete host and issue a recruit card + wallet link.
6. Share the generated card/wallet link with hosts so they spend directly instead of collecting receipts.

## Ramp integration notes

The `RampClient` is implemented in:

```text
app/services/ramp_client.py
```

- **Live mode** activates automatically when `RAMP_CLIENT_ID` and `RAMP_CLIENT_SECRET` are present.
- **Demo mode** is used otherwise and still allows full UI workflow testing.
- Card provisioning calls currently target:
  - token URL: `RAMP_TOKEN_URL`
  - virtual card endpoint: `{RAMP_API_BASE_URL}/cards/virtual`

Adjust payload/paths if your Ramp tenant uses different endpoints.

## Project layout

```text
app/
  main.py                    # HTTP routes + workflow orchestration
  config.py                  # env loading and settings
  db.py                      # sqlite schema + operations
  services/
    link_importer.py         # roster/schedule ingestion from URLs
    ramp_client.py           # Ramp API wrapper + demo fallback
    travel_planner.py        # hotel suggestion helper (Tavily-assisted)
    notifications.py         # assignment message helper
templates/
  base.html
  index.html
  wallet_card.html
static/
  styles.css
```

## Remaining setup for you

The implementation is done; your remaining steps are:
1. Add API keys/secrets to `.env`.
2. Run the server and start using import + travel + recruiting workflows.
