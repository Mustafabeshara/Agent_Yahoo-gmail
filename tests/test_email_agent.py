import asyncio
import pytest

from email_agent.main import (
    EmailAgentContext,
    update_outreach_contact_in_context,
    generate_weekly_supplier_report,
    add_medical_summary_to_context,
    generate_biweekly_medical_trend_report,
)

from agents.run_context import RunContextWrapper


@pytest.mark.asyncio
async def test_supplier_workflow():
    ctx = EmailAgentContext()
    wrapper = RunContextWrapper(ctx)

    # Add contact
    await update_outreach_contact_in_context(
        wrapper,
        name="Acme Medical",
        email="sales@acmemed.com",
        status="initial_sent",
    )

    # Generate weekly report
    report_text = await generate_weekly_supplier_report(wrapper)

    assert "Acme Medical" in report_text
    assert ctx.weekly_report, "Weekly report should be stored in context"


@pytest.mark.asyncio
async def test_medical_trend_reporting():
    ctx = EmailAgentContext()
    wrapper = RunContextWrapper(ctx)

    # Add a medical summary
    await add_medical_summary_to_context(
        wrapper,
        source_email_subject="Breakthrough Therapy X",
        summary="A new therapy shows promise in trials.",
        trend="Gene Therapy",
    )

    # Generate biweekly report
    report_text = await generate_biweekly_medical_trend_report(wrapper)

    assert "Gene Therapy" in report_text
    assert ctx.bi_weekly_report, "Bi-weekly report should be stored in context" 