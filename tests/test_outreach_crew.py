from app.services.outreach_crew import OutreachCrew


def test_outreach_crew_fallback():
    result = OutreachCrew().run("Acme", "Founder", "AI outreach automation")
    assert result.crew == "outreach"
    assert len(result.steps) == 3
    assert result.subject
    assert result.body
