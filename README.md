# Email Monitoring Agent

A multi-agent workflow (built with [openai-agents-python](https://github.com/openai/openai-agents-python)) that does the following on a single **`python email_agent/main.py`** run:

1. Monitors a Yahoo! Mail inbox, triages each new e-mail, and hands it off to specialist agents (medical-news summarisation, response drafting, KOC tender attachment download, supplier outreach).
2. Keeps a shared, structured state (`EmailAgentContext`) that all agents can read & update.
3. Runs a business-development outreach workflow with automatic follow-ups.
4. Produces two reports every cycle:   
   • **Weekly supplier-outreach report**   
   • **Bi-weekly medical-trend report**

---

## Features

| Capability | How it works |
|------------|--------------|
| Yahoo inbox triage | `read_yahoo_emails()` + **Triage Agent**
| Medical-news processing | **Medical News Agent** → `summarize_and_identify_trends()` → `add_medical_summary_to_context()`
| KOC tender handling | **KOC Tender Agent** → `read_gmail_and_download_attachments()`
| Response drafting | **Response Drafting Agent** → `draft_response()`
| Supplier outreach & follow-ups | **Supplier Outreach Agent** → `draft_*` → `send_email()` → `update_outreach_contact_in_context()`
| Reporting | **Reporting Agent** → `generate_*_report()`

---

## Quick-start

### 1. Clone & install

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r email_agent/requirements.txt
```

### 2. Obtain credentials securely

* **OpenAI** – create an API key in <https://platform.openai.com/account/api-keys>.
* **Yahoo! Mail** – _do **not** use your login password._  Create an **App Password** (Settings → Account Security → "Generate app password") and store it somewhere safe.
* **Gmail (optional)** – if you plan to replace the stub Gmail tool, create OAuth credentials and a `token.json` per the Gmail Python quickstart.

### 3. Export environment variables

```bash
# UNIX / macOS / WSL
export OPENAI_API_KEY="sk-..."
export YAHOO_EMAIL="your_address@yahoo.com"
export YAHOO_PASSWORD="16-char-app-password"

# Windows (PowerShell)
setx OPENAI_API_KEY "sk-..."
setx YAHOO_EMAIL "your_address@yahoo.com"
setx YAHOO_PASSWORD "16-char-app-password"
```

> 🛡 **Why environment variables?**  They keep secrets **out of your codebase & git history**.  You can also use a `.env` file and a loader such as [python-dotenv](https://pypi.org/project/python-dotenv/) or your OS keychain/secret-manager.

### 4. Run the agent

```bash
python -m email_agent.main
```

You'll see console logs for each agent/tool call followed by the final `EmailAgentContext` JSON.

---

## Securing your Yahoo! account

1. **Enable 2-factor authentication** on your Yahoo account if you haven't already.
2. **Generate an App Password** (not your main password):  
   * Account Security → _Generate app password_ → choose "Other" → name it e.g. "Email Monitoring Bot" → copy the 16-character password.
3. **Store the app password in an environment variable (`YAHOO_PASSWORD`)** or your system's secret store (Keychain, Windows Credential Manager, AWS Secrets Manager, etc.).
4. **Never commit credentials** to git.  Add `.env` or shell profile files to your `.gitignore`.
5. The script logs high-level activity only; it **does not store or print full e-mail bodies** unless you change the `print` statements.

---

## Scheduling (optional)

For production you'll likely want the script to run every 5-15 minutes.

* **cron** (Linux/macOS):
  ```cron
  */10 * * * * cd /path/to/Email\ Monitoring && /usr/bin/env bash -c 'source .venv/bin/activate && python -m email_agent.main'
  ```
* **Windows Task Scheduler** – create an *Action* that runs `python -m email_agent.main` inside your project directory.
* **Docker / Kubernetes / ECS scheduled task** – package the scripts into a container and schedule with your orchestrator.

---

## Extending

* Replace the Gmail stub with the real Gmail API (see `google-api-python-client`).
* Add an SMTP tool for the Yahoo or a transactional e-mail API (SendGrid, SES) so agents can **actually send** the drafted e-mails.
* Persist `EmailAgentContext` in a database or S3 so the state survives restarts.
* Build a small Streamlit or FastAPI UI to review and approve drafted responses.

---

## License

MIT © 2024 Your-Name 

from dotenv import load_dotenv
load_dotenv()           # ← finds and loads .env in the CWD 

# .env  (DON'T commit—already in .gitignore)
OPENAI_API_KEY=sk-...
YAHOO_EMAIL=your_address@yahoo.com
YAHOO_PASSWORD=16-char-app-password

---

## Git Repository

The project has been initialized and committed to the following Git repository:

```
origin  https://github.com/Mustafabeshara/Agent_Yahoo-gmail.git
```