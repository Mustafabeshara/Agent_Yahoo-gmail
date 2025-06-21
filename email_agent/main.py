from __future__ import annotations as _annotations

import asyncio
import random
import uuid
import typing
import os
from datetime import datetime, timedelta
from typing import List, Literal

from pydantic import BaseModel, Field
from openai.types.responses import ResponseFunctionToolCall
from imap_tools.mailbox import MailBox
from imap_tools.query import AND

from agents import (
    Agent,
    HandoffOutputItem,
    ItemHelpers,
    MessageOutputItem,
    RunContextWrapper,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
    TResponseInputItem,
    function_tool,
    handoff,
    trace,
)
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# --- Agent Context ---
# This class holds the state of our email agent's operations.

class OutreachContact(BaseModel):
    name: str
    email: str
    status: Literal["initial_sent", "follow_up_1_sent", "follow_up_2_sent", "replied", "unresponsive"] = "initial_sent"
    last_contact_date: datetime

class MedicalNewsSummary(BaseModel):
    source_email_subject: str
    summary: str
    trend: str
    date: datetime

class EmailAgentContext(BaseModel):
    outreach_list: List[OutreachContact] = Field(default_factory=list)
    medical_summaries: List[MedicalNewsSummary] = Field(default_factory=list)
    weekly_report: List[str] = Field(default_factory=list)
    # Stores aggregated bi-weekly medical trend reports as plain text.
    bi_weekly_report: List[str] = Field(default_factory=list)

# --- Email Credentials ---
# IMPORTANT: Set these environment variables before running the agent.
# For security, use an "App Password" for YAHOO_PASSWORD, not your main password.
# You can generate one in your Yahoo account's security settings.
# export YAHOO_EMAIL="your_yahoo_email@yahoo.com"
# export YAHOO_PASSWORD="your_yahoo_app_password"

YAHOO_IMAP_SERVER = "imap.mail.yahoo.com"

# --- Tools ---
# These are the functions our agents can use.

async def read_yahoo_emails() -> list[dict] | str:
    """
    Connects to the Yahoo IMAP server and reads unseen emails.
    Returns a list of email dictionaries or an error message string.
    """
    email_address = os.getenv("YAHOO_EMAIL")
    password = os.getenv("YAHOO_PASSWORD")

    if not email_address or not password:
        return "Error: YAHOO_EMAIL and YAHOO_PASSWORD environment variables are not set."

    emails = []
    try:
        with MailBox(YAHOO_IMAP_SERVER).login(email_address, password, 'INBOX') as mailbox:
            # Fetch unseen emails. The `mark_seen=True` default will mark them as seen.
            for msg in mailbox.fetch(AND(seen=False)):
                emails.append({
                    "from": msg.from_,
                    "subject": msg.subject,
                    "body": msg.text or msg.html
                })
        return emails
    except Exception as e:
        return f"Error connecting to Yahoo IMAP or fetching emails: {e}"

@function_tool
async def read_gmail_and_download_attachments(subject_keyword: str) -> str:
    """Reads Gmail, finds emails with a specific keyword, and downloads their attachments."""
    print(f"TOOL: Checking Gmail for emails with '{subject_keyword}' and downloading attachments...")
    # In the future, this will use the Gmail API.
    return "Successfully downloaded 3 attachments from KOC tender emails."

@function_tool
async def send_email(to: str, subject: str, body: str) -> str:
    """Sends an email."""
    print(f"TOOL: Sending email to {to} with subject '{subject}'")
    print(f"BODY:\n{body}")
    return "Email sent successfully."

@function_tool
async def draft_response(email_body: str) -> str:
    """Drafts a response to an email."""
    print("TOOL: Drafting a response...")
    return f"This is a drafted response to:\n---\n{email_body[:50]}...\n---"

@function_tool
async def summarize_and_identify_trends(text: str) -> str:
    """Summarizes a text and identifies key trends."""
    print("TOOL: Summarizing text and identifying trends...")
    return "Summary: New treatment shows promise. Trend: AI in drug discovery is growing."

@function_tool
async def add_medical_summary_to_context(
    context: RunContextWrapper[EmailAgentContext],
    source_email_subject: str,
    summary: str,
    trend: str,
) -> str:
    """
    Adds a medical news summary to the shared context.

    Args:
        source_email_subject: The subject of the source email.
        summary: The summary of the article.
        trend: The key trend identified.
    """
    new_summary = MedicalNewsSummary(
        source_email_subject=source_email_subject,
        summary=summary,
        trend=trend,
        date=datetime.now(),
    )
    context.context.medical_summaries.append(new_summary)
    return "Successfully added medical summary to context."

@function_tool
async def draft_supplier_outreach_email(supplier_name: str) -> str:
    """
    Drafts a personalized outreach email to a potential supplier.

    Args:
        supplier_name: The name of the supplier company.
    """
    print(f"TOOL: Drafting outreach email for {supplier_name}...")
    template = (
        f"Subject: Exploring Distribution Opportunities in Kuwait with {supplier_name}\n\n"
        f"Dear {supplier_name} Team,\n\n"
        "My name is [Your Name] and I am the [Your Title] at [Your Company]. We are a leading distributor of medical supplies in Kuwait, and we have been following your company's impressive work and innovative products with great interest.\n\n"
        "We believe that your products would be an excellent addition to our portfolio, and we are confident that we can establish a strong market presence for you in Kuwait. We would be very interested in discussing the possibility of a distribution partnership.\n\n"
        "Would you be available for a brief call next week to explore this further?\n\n"
        "Best regards,\n"
        "[Your Name]\n"
        "[Your Title]\n"
        "[Your Company]\n"
        "[Your Contact Information]"
    )
    return template

@function_tool
async def draft_follow_up_email(supplier_name: str) -> str:
    """Drafts a brief, friendly follow-up email."""
    print(f"TOOL: Drafting follow-up email for {supplier_name}...")
    template = (
        f"Subject: Checking In: Distribution Opportunities in Kuwait\n\n"
        f"Dear {supplier_name} Team,\n\n"
        "I hope this email finds you well. I'm writing to follow up on my previous message regarding a potential distribution partnership in Kuwait.\n\n"
        "We are very enthusiastic about the possibility of working together and would be happy to answer any questions you might have.\n\n"
        "Best regards,\n"
        "[Your Name]"
    )
    return template

@function_tool
async def update_outreach_contact_in_context(
    context: RunContextWrapper[EmailAgentContext],
    name: str,
    email: str,
    status: Literal["initial_sent", "follow_up_1_sent", "follow_up_2_sent", "replied", "unresponsive"],
) -> str:
    """Adds or updates a supplier contact in the outreach list in the shared context."""
    # Check if contact already exists
    for contact in context.context.outreach_list:
        if contact.email == email:
            contact.status = status
            contact.last_contact_date = datetime.now()
            return f"Successfully updated contact {name} with status {status}."

    # If not, add new contact
    new_contact = OutreachContact(
        name=name,
        email=email,
        status=status,
        last_contact_date=datetime.now(),
    )
    context.context.outreach_list.append(new_contact)
    return f"Successfully added new contact {name} to outreach list."

# ---------------------------------------------------------------------------
# Reporting tools
# ---------------------------------------------------------------------------

@function_tool
async def generate_weekly_supplier_report(
    context: RunContextWrapper[EmailAgentContext],
) -> str:
    """Creates a weekly supplier outreach report and saves it to the context."""
    today = datetime.now().date()

    if not context.context.outreach_list:
        report = f"Weekly Supplier Outreach Report ({today}):\n\nNo supplier outreach activity this week."
    else:
        header = f"Weekly Supplier Outreach Report ({today})"
        divider = "-" * len(header)

        lines = [header, divider]

        status_counts: dict[str, int] = {}
        for contact in context.context.outreach_list:
            status_counts[contact.status] = status_counts.get(contact.status, 0) + 1
            days_since_contact = (datetime.now() - contact.last_contact_date).days
            lines.append(
                f"• {contact.name} ({contact.email}) – {contact.status.replace('_', ' ').title()} – {days_since_contact} days since last contact"
            )

        # Add a summary section
        lines.append("\nSummary:")
        for status, count in status_counts.items():
            lines.append(f"  - {status.replace('_', ' ').title()}: {count}")

        # Identify unresponsive suppliers (no reply after second follow-up)
        unresponsive = [c for c in context.context.outreach_list if c.status == "unresponsive"]
        if unresponsive:
            lines.append("\nUnresponsive Suppliers:")
            for contact in unresponsive:
                lines.append(f"  • {contact.name} ({contact.email})")

        report = "\n".join(lines)

    # Persist to context
    context.context.weekly_report.append(report)
    return report

@function_tool
async def generate_biweekly_medical_trend_report(
    context: RunContextWrapper[EmailAgentContext],
) -> str:
    """Creates a bi-weekly medical trend report and saves it to the context."""
    today = datetime.now().date()
    cutoff = datetime.now() - timedelta(days=14)

    recent_summaries = [s for s in context.context.medical_summaries if s.date >= cutoff]

    if not recent_summaries:
        report = (
            f"Bi-Weekly Medical Trends Report ({today}):\n\nNo medical news summaries recorded in the last 14 days."
        )
    else:
        header = f"Bi-Weekly Medical Trends Report ({today})"
        divider = "-" * len(header)
        lines = [header, divider]

        # Group summaries by trend
        trend_groups: dict[str, list[MedicalNewsSummary]] = {}
        for summary in recent_summaries:
            trend_groups.setdefault(summary.trend, []).append(summary)

        for trend, items in trend_groups.items():
            lines.append(f"\nTrend: {trend} – {len(items)} article(s)")
            for item in items:
                lines.append(f"  • {item.source_email_subject}: {item.summary}")

        report = "\n".join(lines)

    # Persist to context
    context.context.bi_weekly_report.append(report)
    return report

# ---------------------------------------------------------------------------
# Reporting Agent
# ---------------------------------------------------------------------------

reporting_agent = Agent(
    name="Reporting Agent",
    instructions=(
        "Your job is to produce two reports:\n"
        "1. A weekly supplier outreach report by calling 'generate_weekly_supplier_report'.\n"
        "2. A bi-weekly medical trend report by calling 'generate_biweekly_medical_trend_report'.\n\n"
        "Call each tool and return their output. Do not provide any commentary beyond the tool calls."
    ),
    tools=[generate_weekly_supplier_report, generate_biweekly_medical_trend_report],
    model="gpt-3.5-turbo",
)

# --- Agents ---

# 1. KOC Tender Agent
koc_tender_agent = Agent(
    name="KOC Tender Agent",
    instructions="You have one job: use the 'read_gmail_and_download_attachments' tool to find emails with the keyword 'KOC tenders' and download their attachments. Do not use any other keywords.",
    tools=[read_gmail_and_download_attachments],
    model="gpt-3.5-turbo",
)

# 2. Medical News Agent
medical_news_agent = Agent(
    name="Medical News Agent",
    instructions="You specialize in medical news. First, use the 'summarize_and_identify_trends' tool to process the article. Then, use the 'add_medical_summary_to_context' tool to save the structured summary, including the original email subject, the summary, and the trend.",
    tools=[summarize_and_identify_trends, add_medical_summary_to_context],
    model="gpt-3.5-turbo",
)

# 3. Response Drafting Agent
response_drafting_agent = Agent(
    name="Response Drafting Agent",
    instructions="You specialize in drafting email responses for approval.",
    tools=[draft_response],
    model="gpt-3.5-turbo",
)

# 4. Supplier Outreach Agent
supplier_outreach_agent = Agent(
    name="Supplier Outreach Agent",
    instructions=(
        "You are a business development specialist. Your tasks involve supplier outreach.\n"
        "If asked to contact a *new* supplier:\n"
        "1. Use 'draft_supplier_outreach_email' to generate the initial email.\n"
        "2. Use 'send_email' to send it.\n"
        "3. Use 'update_outreach_contact_in_context' to log the status as 'initial_sent'.\n\n"
        "If asked to send a *follow-up* email:\n"
        "1. Use 'draft_follow_up_email' to generate the follow-up message.\n"
        "2. Use 'send_email' to send it.\n"
        "3. Use 'update_outreach_contact_in_context' to log the new status (e.g., 'follow_up_1_sent')."
    ),
    tools=[
        draft_supplier_outreach_email,
        draft_follow_up_email,
        send_email,
        update_outreach_contact_in_context,
    ],
    model="gpt-3.5-turbo",
)

# 5. Triage Agent (The first agent to see an email)
triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "You are an email routing specialist. Your job is to analyze an email and hand it off to the correct agent. You must choose one of the following agents:\n\n"
        "- 'Medical News Agent': Use for emails that are medical journals, newsletters, or health articles.\n"
        "- 'KOC Tender Agent': Use for emails that are specifically about 'KOC tenders'.\n"
        "- 'Response Drafting Agent': Use for general inquiries or supplier emails that need a direct response.\n\n"
        "Based on the email content, select the single best agent to hand off to."
    ),
    handoffs=[koc_tender_agent, medical_news_agent, response_drafting_agent, supplier_outreach_agent],
    model="gpt-3.5-turbo",
)

# --- Main Application Logic ---

async def process_yahoo_emails(context: EmailAgentContext):
    """
    - Monitors Yahoo emails.
    - Drafts responses for approval.
    - Identifies medical news, summarizes it, and updates the context.
    """
    print("\n--- Task: Processing Yahoo Emails ---")
    
    new_emails = await read_yahoo_emails()

    if isinstance(new_emails, str):
        print(f"Could not fetch emails: {new_emails}")
        return

    if not new_emails:
        print("No new emails to process.")
        return

    print(f"Fetched {len(new_emails)} new email(s).")

    for email in new_emails:
        print(f"\nProcessing email from {email['from']} with subject: '{email['subject']}'")
        email_content = f"From: {email['from']}\nSubject: {email['subject']}\n\n{email['body']}"
        
        conversation_id = uuid.uuid4().hex[:16]
        with trace("Email Processing", group_id=conversation_id):
            input_items = [{"role": "user", "content": email_content}]
            result = await Runner.run(
                triage_agent, typing.cast(list[TResponseInputItem], input_items), context=context
            )

            for new_item in result.new_items:
                agent_name = new_item.agent.name
                if isinstance(new_item, MessageOutputItem):
                    print(f"{agent_name}: {ItemHelpers.text_message_output(new_item)}")
                elif isinstance(new_item, HandoffOutputItem):
                    print(f"HANDOFF: From {new_item.source_agent.name} to {new_item.target_agent.name}")
                elif isinstance(new_item, ToolCallItem):
                    if isinstance(new_item.raw_item, ResponseFunctionToolCall):
                        tool_name = new_item.raw_item.name
                        tool_args = new_item.raw_item.arguments
                        print(f"{agent_name}: Calling tool {tool_name}({tool_args})")
                    else:
                        print(f"{agent_name}: Calling a non-function tool: {type(new_item.raw_item).__name__}")
                elif isinstance(new_item, ToolCallOutputItem):
                    print(f"{agent_name}: Tool output: {new_item.output}")
                else:
                    print(f"{agent_name}: Skipping item: {new_item.__class__.__name__}")
    
    print("--- Task: Yahoo Emails Complete ---")


async def process_koc_tenders(context: EmailAgentContext):
    """
    - Accesses Gmail to download attachments from KOC tenders.
    """
    print("\n--- Task: Processing KOC Tenders ---")
    # We don't call the tool directly. We run the agent responsible for it.
    prompt = "Check for new emails about KOC tenders and download their attachments."
    input_items = [{"role": "user", "content": prompt}]
    await Runner.run(koc_tender_agent, typing.cast(list[TResponseInputItem], input_items), context=context)
    print("--- Task: KOC Tenders Complete ---")


async def manage_supplier_outreach(context: EmailAgentContext):
    """
    - Drafts outreach emails to new suppliers.
    - Sends follow-ups based on the schedule (2 days and 7 days).
    """
    print("\n--- Task: Managing Supplier Outreach ---")

    # 1. Simulate getting a list of new suppliers to contact
    new_suppliers = [
        {"name": "Innovate MedTech", "email": "contact@innovatemed.com"},
        {"name": "Global Pharma", "email": "inquiries@globalpharma.com"},
    ]

    # 2. Contact new suppliers that are not already in our list
    for supplier in new_suppliers:
        is_new = not any(c.email == supplier["email"] for c in context.outreach_list)
        if is_new:
            print(f"New supplier found: {supplier['name']}. Initiating outreach.")
            prompt = (
                f"Contact the new supplier named '{supplier['name']}' at the email address '{supplier['email']}'."
            )
            await Runner.run(supplier_outreach_agent, [{"role": "user", "content": prompt}], context=context)

    # 3. Check for and send follow-ups
    today = datetime.now()
    for contact in context.outreach_list:
        days_since_contact = (today - contact.last_contact_date).days
        
        # Follow up after 2 days
        if contact.status == "initial_sent" and days_since_contact >= 2:
            print(f"Contact {contact.name} needs a 2-day follow-up. Sending...")
            prompt = (
                f"Send a 2-day follow-up email to '{contact.name}' at '{contact.email}'. "
                "Keep it brief and friendly, just checking in on our previous message."
            )
            # We can reuse the same outreach agent, the prompt will guide it.
            # For a more complex system, we might have a dedicated follow-up agent.
            await Runner.run(supplier_outreach_agent, [{"role": "user", "content": prompt}], context=context)
            # The agent itself should update the context to 'follow_up_1_sent'
            # We need to add instructions for this. For now, we'll assume it does.

    print("--- Task: Supplier Outreach Complete ---")


async def generate_reports(context: EmailAgentContext):
    """
    - Generates a weekly report of unresponsive suppliers.
    - Generates a bi-weekly report of medical trends.
    """
    print("\n--- Task: Generating Reports ---")

    # In a real system, you'd check whether it's the correct day to run these. For this demo
    # we'll run both every cycle.
    prompt = "Please generate this cycle's weekly and bi-weekly reports."
    await Runner.run(
        reporting_agent,
        [{"role": "user", "content": prompt}],
        context=context,
    )

    print("--- Task: Reports Complete ---")


async def main():
    print("Initializing Email Agent...")
    agent_context = EmailAgentContext()

    # In a real application, this main function would be run on a schedule (e.g., every 5-15 minutes by a cron job)
    await process_yahoo_emails(agent_context)
    await process_koc_tenders(agent_context)
    await manage_supplier_outreach(agent_context)
    await generate_reports(agent_context)

    print("\n--- Full Simulation Cycle Complete ---")
    print("Final Context:", agent_context.model_dump_json(indent=2))


if __name__ == "__main__":
    # To run this, you'll need to set the OPENAI_API_KEY environment variable.
    # For example:
    # export OPENAI_API_KEY="your_key_here"
    # python email_agent/main.py
    
    # Note: Pydantic V2 is required by the agents SDK.
    # You might need to run `pip install "pydantic>=2"`
    
    asyncio.run(main()) 