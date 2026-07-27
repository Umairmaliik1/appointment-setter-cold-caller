# Appointment-Setter-Cold-Caller

Production FastAPI service for tenant-scoped outbound cold-calling campaigns using Twilio + LiveKit SIP, with shared auth/data model from the main Appointment Setter platform.

## Core Features

- Tenant-scoped campaign management with strict lifecycle controls.
- CSV contact ingestion with normalization, dedupe, and DNC suppression.
- Per-campaign intro audio (S3-compatible upload flow).
- Sequential dialing orchestration (persisted state, no in-memory campaign state).
- Twilio status/webhook handling with signature verification.
- LiveKit SIP bridge support for AI voice handoff after intro audio.
- Shared JWT auth model (admin cross-tenant; regular users own-tenant).

## Run Locally

1. Copy env:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start API:

```bash
uvicorn app.main:app --reload --port 8010
```

## API Prefix

All endpoints are under:

`/api/v1/cold-caller/*`

