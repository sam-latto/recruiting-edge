# RecruitingEdge

AI-powered recruiting command center for MBA students. Built to demonstrate end-to-end multi-agent architecture using the Anthropic SDK — every architectural decision is deliberate and defensible in a technical interview.

## What it does

| Feature | Description |
|---|---|
| **STAR Story Builder** | Conversational agent that guides you through building Situation-Task-Action-Result stories for resume bullets |
| **Job Manager** | Add jobs from a URL, pasted text, or PDF; LLM extracts structured details; Kanban pipeline view |
| **Bullet Tailoring** | Conversational agent rewrites bullets for a specific job posting, grounded in your STAR story bank |
| **ATS Scorer** | Simulates Workday/Greenhouse/Lever scoring: keyword frequency, skills coverage, title alignment, format signals |
| **Application Tracker** | Kanban board + Gmail integration to auto-detect confirmation emails |

## Architecture

Five stateless agents, each with a single responsibility:

```
tools/          # External integrations (PDF, web, Gmail API)
agents/         # LLM agents — receive data, return structured output, never own state
db/             # All persistence — agents never write to the DB directly
pages/          # Streamlit UI only
scheduler/      # APScheduler background Gmail scan
```

Agents communicate through the database and explicit function arguments — not shared state. This makes each agent independently testable and gives each a distinct failure mode and retry strategy.

## Quick start

```bash
# 1. Clone and install dependencies
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and DATABASE_PATH

# 3. Run
streamlit run app.py
```

## Environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Required for all agents |
| `DATABASE_PATH` | Path to SQLite file (default: `./recruitingedge.db`) |
| `GOOGLE_CLIENT_ID` | Required for Gmail integration |
| `GOOGLE_CLIENT_SECRET` | Required for Gmail integration |
| `GOOGLE_REDIRECT_URI` | OAuth callback (default: `http://localhost:8501/oauth/callback`) |

## Gmail setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the Gmail API
3. Create an OAuth 2.0 Client ID (Desktop application)
4. Download `credentials.json` and place it in the project root
5. First scan triggers a browser consent window; subsequent runs use the saved `token.json`

## Tech stack

Python 3.11+ · Anthropic SDK · Streamlit · SQLite · PyMuPDF · BeautifulSoup · Google Gmail API · APScheduler

## Design decisions

**Why five agents instead of one?** Each agent has a different latency profile, failure mode, and retry strategy. The Gmail agent runs on a schedule; the STAR agent runs interactively; the scraping agent fails silently. Combining them would make the failure surface unpredictable.

**Why is tailoring conversational?** One-shot rewrites produce polished-sounding but factually thin bullets. The conversational loop forces the user to confirm which skill to demonstrate and verify the rewrite reflects real experience.

**Why does the ATS agent simulate ATS behavior rather than use semantic similarity?** Real ATS systems do keyword frequency and skills taxonomy lookup — not full semantic understanding. Optimizing for semantic similarity gives false confidence.

**Why SQLite for v1?** Zero config, ships with Python. The schema is fully normalized and PostgreSQL-compatible — the only change needed for v2 is the connection string.
