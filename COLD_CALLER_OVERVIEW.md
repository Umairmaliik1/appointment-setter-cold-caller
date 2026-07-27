# Cold Caller Overview

## Tech Stack
- Backend: FastAPI + Pydantic + Uvicorn
- Data: Firebase Firestore (campaigns, contacts, attempts, DNC, runtime events)
- Telephony: Twilio Voice (outbound, AMD, webhooks, status callbacks)
- AI bridge: LiveKit SIP dispatch after intro audio
- Cache/runtime handoff: Redis
- File storage: S3-compatible object storage (intro audio)
- Infra: Docker, Docker Compose, GitHub Actions CI, Pytest

## Architecture (High Level)
- `API Layer` (`app/api/v1/routers/*`): authenticated campaign/DNC endpoints + Twilio webhooks
- `Service Layer` (`app/services/*`): campaign logic, compliance checks, dialer orchestration, Twilio/S3/LiveKit integrations
- `Repository Layer` (`app/repositories/*`): Firestore persistence and query operations
- `Worker Behavior`: sequential dialing with persistent state + lease-based safety (no in-memory-only orchestration)

## Technical Flow
1. User creates campaign (tenant-scoped, voice-agent bound).
2. User uploads contacts CSV (`phone_number` required) and intro audio.
3. User starts campaign manually.
4. Dialer picks next eligible contact (window, retry, DNC, attempt caps).
5. Twilio outbound call is created with AMD enabled.
6. Twilio webhook returns TwiML: `<Play>` intro audio first, then `<Dial><Sip>` to LiveKit.
7. AI session runs through LiveKit worker using selected voice agent behavior.
8. Twilio status callback updates attempt/contact/campaign state.
9. Dialer continues sequentially until campaign completes/pauses/cancels.

## Why This Design Is Best (for this platform)
- Production-safe: state is persisted; process restarts do not lose campaign progress.
- Compliance-first: DNC + calling windows + retry/attempt limits enforced before every attempt.
- Clear separation: standalone cold-caller service, still compatible with existing frontend/auth/data.
- Cost/control: strict sequential dialing for predictable throughput and lower blast risk.
- Telephony correctness: standard Twilio webhook + signature validation + status callback model.

## `.env` Setup (Cold Caller)
1. Copy:
   - `cp .env.example .env` (Linux/macOS)
   - `Copy-Item .env.example .env` (PowerShell)
2. Set required values:
   - `SECRET_KEY` (must match main backend JWT signing key)
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_PRIVATE_KEY`
   - `FIREBASE_CLIENT_EMAIL`
   - `TWILIO_WEBHOOK_BASE_URL` (public HTTPS URL of cold-caller API in non-local environments)
   - `LIVEKIT_SIP_DOMAIN`
3. Set storage values for intro audio:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `S3_BUCKET`
   - Optional: `S3_ENDPOINT_URL`, `S3_PUBLIC_BASE_URL`
4. Optional runtime tuning:
   - `REDIS_URL`
   - `CALL_CONFIG_TTL_SECONDS`
   - `PRESIGNED_URL_EXPIRES_SECONDS`
   - `MAX_AUDIO_UPLOAD_MB`
   - `ENVIRONMENT`, `DEBUG`, `LOG_LEVEL`, `API_HOST`, `API_PORT`

