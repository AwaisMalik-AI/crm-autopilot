# CRM Autopilot

**AI-powered CRM and outreach automation** for freelancers and agencies — contact and lead management, AI-assisted lead scoring, email sequences with mailbox warmup, campaign analytics, pipeline stages, smart lists, scheduled daily reports, and signed webhooks.

**Latest:** Outreach crew (`POST /api/crews/outreach`) — researcher → copywriter → compliance, plus Celery worker `crm.run_outreach_crew`.

Backend-only **FastAPI** service designed as a **portfolio-grade** reference: structured layers (routes → services → models), **no hardcoded secrets**, Docker Compose with **Celery worker + beat**, and clear extension points (LLM, tracking providers).

## Architecture (ASCII)

```
                         +------------------+
                         |    Contacts      |
                         +--------+---------+
                                  |
                                  v
+----------------+        +-------+--------+        +-------------------+
| Email accounts |------->|  Warmup engine |------>| Sequence automation|
+-------+--------+        +-------+--------+        +---------+---------+
        |                         |                           |
        |                         v                           v
        |                 +-------+--------+        +---------+---------+
        +---------------->|  Email send   |-------->|  Event tracking   |
                          +---------------+         +---------+---------+
                                                              |
   +------------------+                                       v
   | Lead scoring (AI)|<------------------------------+--------+--------+
   +--------+---------+                              |   Analytics /     |
            |                                         |   daily reports   |
            v                                         +-------------------+
   +--------+---------+
   | Pipeline stages  |
   +------------------+
            ^
            |
   +--------+---------+
   |   Smart lists    |
   +------------------+
```

**Flow:** contacts feed **lead scoring** (rules + optional LLM narrative) and **pipeline** stages. **Email accounts** go through **warmup** caps before **sequences** send templated steps. Outcomes land in **email events** and **lead activities**, powering **analytics** and **daily reports**. **Smart lists** segment contacts with JSON rules.

## Email warmup strategy

- Each `EmailAccount` tracks `warmup_stage`, `warmup_max_per_day`, and `sent_today`.
- When `WARMUP_ENABLED` is true, the effective daily send cap is the **minimum** of the account `daily_limit` and a **ramped ceiling** derived from warmup fields (see `EmailEngine.check_warmup_eligibility`).
- **Celery** task `warmup_advance` runs daily (01:00 UTC) to gradually increase allowed volume so new domains/IPs are less likely to trigger provider throttling or spam placement.
- **Midnight UTC** `counter_reset` zeroes `sent_today` for all accounts.

## Pipeline stages

Leads move through:

`new` → `contacted` → `qualified` → `proposal` → `negotiation` → `won` | `lost`

Stage changes are logged as `LeadActivity` records (`stage_change`) for reporting and scoring recency.

## Smart list filter operators

Filters are JSON: `{ "combiner": "and" | "or", "rules": [ ... ] }`.

Each rule: `{ "field", "operator", "value" }`.

| Operator       | Meaning |
|----------------|---------|
| `equals`       | Case-insensitive string equality |
| `contains`     | Substring match |
| `greater_than` | Numeric comparison |
| `less_than`    | Numeric comparison |
| `in_list`      | Value in list or comma-separated string |
| `not_empty`    | Field present and non-blank |
| `date_before`  | Date/datetime before value (ISO date) |
| `date_after`   | Date/datetime after value |

Fields support `custom.*` for keys inside `Contact.custom_fields`.

## Celery beat schedule

| Job | Schedule (UTC) | Task |
|-----|----------------|------|
| Process sequence queue | Every 15 minutes | `process_pending_sequences` |
| Warmup advance | Daily 01:00 | `warmup_task` |
| Reset daily counters | Daily 00:00 | `counter_reset` |
| Refresh smart lists | Daily 03:00 | `refresh_all_smart_lists` |
| Generate daily reports | Daily 06:00 | `report_generation` |

## API endpoints (prefix `/api`)

| Area | Method | Path | Description |
|------|--------|------|-------------|
| **Auth** | POST | `/auth/register` | Register user |
| | POST | `/auth/login` | JSON login |
| | POST | `/auth/token` | OAuth2 password form |
| | GET | `/auth/me` | Current user |
| **Contacts** | GET/POST | `/contacts` | List / create |
| | GET/PATCH/DELETE | `/contacts/{id}` | CRUD |
| | POST | `/contacts/import/csv` | CSV import |
| | POST | `/contacts/tags/bulk` | Bulk tag / flags |
| | POST/DELETE | `/contacts/{id}/tags/{tag}` | Tag add/remove |
| **Leads** | GET/POST | `/leads` | List (optional `stage`, `assigned_to`) / create |
| | GET/PATCH | `/leads/{id}` | Detail / update |
| | POST | `/leads/{id}/assign` | Assign to user (`assignee_id` query) |
| | POST | `/leads/{id}/score` | AI/rule score + persist |
| | GET/POST | `/leads/{id}/activities` | Activity history / add |
| **Sequences** | GET/POST | `/sequences` | List / create |
| | GET/PATCH/DELETE | `/sequences/{id}` | CRUD |
| | POST | `/sequences/{id}/enroll` | Enroll contacts |
| | GET | `/sequences/{id}/performance` | Opens/replies/bounces per step |
| | POST | `/sequences/{id}/pause` | Pause |
| | POST | `/sequences/{id}/resume` | Resume |
| **Email accounts** | GET/POST | `/email-accounts` | List / create (encrypts SMTP password) |
| | GET/PATCH/DELETE | `/email-accounts/{id}` | CRUD |
| | POST | `/email-accounts/{id}/health-check` | SMTP login probe |
| | GET | `/email-accounts/{id}/warmup` | Warmup status |
| **Smart lists** | GET/POST | `/smart-lists` | List / create |
| | GET/PATCH/DELETE | `/smart-lists/{id}` | CRUD |
| | POST | `/smart-lists/{id}/refresh` | Recompute count |
| | POST | `/smart-lists/preview` | Preview matching IDs |
| **Analytics** | GET | `/analytics/pipeline` | Pipeline summary (`scope=mine|all`) |
| | GET | `/analytics/email-performance` | Aggregates (`days`) |
| | GET | `/analytics/daily-report` | Daily rollup (`report_date`) |
| | GET | `/analytics/sequences/compare` | Compare sequences |
| **Webhooks** | POST | `/webhooks/email-event` | Tracking events (signed) |
| | POST | `/webhooks/inbound` | New contact from external (signed) |
| **Health** | GET | `/health` | Liveness |

Webhook signature: **HMAC-SHA256** over raw body, hex digest in header **`X-Signature`** (optional prefix `sha256=`).

## Tech stack

- **Python 3.12**, **FastAPI**, **Pydantic v2**, **SQLAlchemy 2** (async API + sync for workers)
- **PostgreSQL** (recommended), **Redis**, **Celery**
- **JWT** auth, **bcrypt** passwords, **Fernet** for stored SMTP secrets
- Optional **LLM** via OpenAI-compatible HTTP API for scoring narrative

## Repository structure

```
app/
  main.py                 # FastAPI app
  core/                   # config, db, security, deps, sync db
  models/                 # User, CRM entities
  schemas/                # Pydantic DTOs
  services/               # LeadScorer, EmailEngine, SmartListEngine, Reporting
  api/routes/             # HTTP routers
  tasks/                  # Celery app + tasks
```

## Quick start (Docker)

1. Copy `.env.example` to `.env` and set **`SECRET_KEY`** (≥32 chars) and **`WEBHOOK_SECRET`** (≥16 chars).
2. `docker compose up --build`
3. API: `http://localhost:8000` — docs: `/docs`

Compose sets `DATABASE_URL` and `REDIS_URL` for services; your `.env` still must define secrets.

## Local development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Set env vars from .env.example, then:
uvicorn app.main:app --reload
```

Celery (separate terminals):

```bash
celery -A app.tasks.celery_app.celery_app worker --loglevel=info
celery -A app.tasks.celery_app.celery_app beat --loglevel=info
```

## Scaling notes

- Run **multiple Celery workers**; **single beat** scheduler.
- Use a managed PostgreSQL + Redis; tune connection pool sizes on the API and workers.
- Put **nginx** or a cloud LB in front for TLS, rate limits, and request size limits.
- Add **Alembic** migrations before multi-node deploys (replace `INIT_DB_ON_STARTUP`).

## CI/CD

GitHub Actions pipeline: lint (ruff) → test (pytest + Postgres + Redis) → Docker build.

## Observability

- **Structured Logging**: JSON logs with request correlation IDs
- **Health Checks**: `GET /health` with DB/Redis/SMTP status
- **Metrics**: Email delivery rates, sequence performance, lead conversion tracking
- **Alerting**: Failed email notifications, bounce rate thresholds

## Cloud Deployment

- **AWS ECS/Fargate**: API + Celery worker + Celery beat containers
- **AWS RDS**: Managed PostgreSQL
- **AWS ElastiCache**: Managed Redis for task queue
- **AWS SES**: Production email sending with domain verification
- **AWS CloudWatch**: Scheduled task monitoring and alerting

## License

MIT (or your choice) — suitable for portfolio use; tighten auth and tenancy before production multi-tenant SaaS.
