# CRM Autopilot — private reference

Internal notes for operators and maintainers. **Do not publish** this file in a public portfolio README link; keep it repo-private or in a separate doc store.

## Environment

- All secrets and connection strings come from environment variables (see `.env.example`).
- `SECRET_KEY` derives Fernet encryption for stored SMTP passwords and signs JWTs.
- `WEBHOOK_SECRET` signs inbound webhook bodies (HMAC-SHA256 hex in `X-Signature`).

## Runtime split

- **API**: async SQLAlchemy + FastAPI (`app.core.database`).
- **Celery**: sync SQLAlchemy (`app.core.sync_db`) — workers must use the same logical DB as the API.

## Operational checklist

1. Copy `.env.example` → `.env`; set `SECRET_KEY`, `WEBHOOK_SECRET`, `DATABASE_URL`, `REDIS_URL`.
2. Prefer **Alembic** for schema migrations in real production; `INIT_DB_ON_STARTUP` is for dev/small deploys only.
3. Scale workers horizontally; keep **one** Celery Beat scheduler.
4. Monitor SMTP health via `POST /api/email-accounts/{id}/health-check` and `health_status` on accounts.
5. Tracking webhooks must resolve `EmailEvent` by `to_email` + optional `message_id` — ensure outbound sends persist `message_id`.

## LLM scoring

- Optional OpenAI-compatible `POST .../chat/completions`. If `LLM_API_URL` / `LLM_API_KEY` unset, scorer still returns rule-based score plus a deterministic fallback explanation.

## Security notes

- Register endpoint is open for portfolio demos; gate it (invite-only or admin-only) before real production.
- Rate-limit auth and webhook routes behind a reverse proxy (nginx, Cloudflare, etc.).
