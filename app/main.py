"""CRM Autopilot — FastAPI application entrypoint."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, auth, contacts, crews, email_accounts, insights, leads, sequences, smart_lists, webhooks
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("INIT_DB_ON_STARTUP", "").lower() in ("1", "true", "yes"):
        await init_db()
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=prefix)
app.include_router(contacts.router, prefix=prefix)
app.include_router(leads.router, prefix=prefix)
app.include_router(sequences.router, prefix=prefix)
app.include_router(email_accounts.router, prefix=prefix)
app.include_router(smart_lists.router, prefix=prefix)
app.include_router(analytics.router, prefix=prefix)
app.include_router(webhooks.router, prefix=prefix)
app.include_router(crews.router, prefix=prefix)
app.include_router(insights.router, prefix=prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
