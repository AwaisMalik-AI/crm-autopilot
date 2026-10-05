from app.services.outreach_crew import OutreachCrew
from app.tasks.celery_app import celery_app


@celery_app.task(name="crm.run_outreach_crew")
def run_outreach_crew_task(company: str, persona: str, offer: str, extras: dict | None = None) -> dict:
    result = OutreachCrew().run(company, persona, offer, extras or {})
    return {
        "crew": result.crew,
        "used_llm": result.used_llm,
        "steps": result.steps,
        "subject": result.subject,
        "body": result.body,
        "compliance_notes": result.compliance_notes,
    }
