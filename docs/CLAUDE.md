# RecruitingEdge — Claude Code Kickoff Document

## What This Project Is

RecruitingEdge is an AI-powered recruiting command center for MBA students. It is also a portfolio project designed to demonstrate end-to-end AI agent architecture to potential employers — particularly tech startups and PM roles. Every architectural decision should be deliberate and defensible in a technical interview.

The goal is not just a working app. It is a codebase that clearly shows:
- Why four distinct agents exist instead of one monolithic AI call
- How agents hand off to each other with explicit input/output contracts
- Why the tailoring agent is conversational rather than one-shot
- How the system fails gracefully when scraping, Gmail, or the LLM misbehaves

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Agent Framework | Anthropic Python SDK (native tool use) |
| Frontend | Streamlit |
| Database | SQLite (v1) |
| PDF Parsing | PyMuPDF (fitz) |
| Web Scraping | BeautifulSoup + Requests |
| Gmail | Google Gmail API + OAuth 2.0 |
| Scheduling | APScheduler |
| Hosting | Railway |
| Config | python-dotenv (.env) |

---

## Project Structure

Build this exact directory layout before writing any feature code:

```
recruitingedge/
├── CLAUDE.md                  # This file — always read first
├── .env.example               # Template for all required env vars
├── .gitignore
├── requirements.txt
├── README.md
│
├── app.py                     # Streamlit entrypoint
│
├── db/
│   ├── __init__.py
│   ├── schema.sql             # All CREATE TABLE statements
│   └── database.py            # Connection management + all query functions
│
├── agents/
│   ├── __init__.py
│   ├── star_agent.py          # STAR Story Agent
│   ├── tailoring_agent.py     # Resume Bullet Tailoring Agent
│   ├── gmail_agent.py         # Gmail Tracker Agent
│   ├── job_scraping_agent.py  # Job Scraping Agent
│   └── ats_agent.py           # ATS Scoring Agent
│
├── tools/
│   ├── __init__.py
│   ├── pdf_parser.py          # PyMuPDF resume + JD PDF extraction
│   ├── web_scraper.py         # BeautifulSoup job URL scraping
│   └── gmail_client.py        # Gmail API OAuth + inbox scanning
│
├── pages/
│   ├── __init__.py
│   ├── onboarding.py          # Resume upload + first-run flow
│   ├── star_builder.py        # STAR Story Builder UI
│   ├── job_manager.py         # Job Posting Manager UI
│   ├── tailoring.py           # Bullet Tailoring Agent UI
│   ├── tracker.py             # Kanban Application Tracker UI
│   └── ats_scorer.py          # ATS Resume Scorer UI
│
├── scheduler/
│   ├── __init__.py
│   └── gmail_scheduler.py     # APScheduler daily Gmail scan
│
└── tests/
    ├── test_db.py
    ├── test_agents.py
    └── test_tools.py
```

---

## Database Schema

Use this exact schema in `db/schema.sql`. Run it once on init.

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    resume_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS star_stories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    original_bullet TEXT NOT NULL,
    situation TEXT,
    task TEXT,
    action TEXT,
    result TEXT,
    is_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_applications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    date_applied DATE,
    status TEXT DEFAULT 'applied',
    job_url TEXT,
    jd_text TEXT,
    notes TEXT,
    next_steps TEXT,
    source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tailored_bullets (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES job_applications(id),
    original_bullet TEXT NOT NULL,
    tailored_bullet TEXT,
    target_skill TEXT,
    recommended_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES job_applications(id),
    name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    linkedin TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ats_scores (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES job_applications(id),
    overall_score INTEGER NOT NULL,
    keyword_score INTEGER,
    skills_score INTEGER,
    experience_score INTEGER,
    format_score INTEGER,
    matched_keywords TEXT,       -- JSON array of matched keywords
    missing_keywords TEXT,       -- JSON array of missing keywords
    matched_skills TEXT,         -- JSON array of matched skills
    missing_skills TEXT,         -- JSON array of missing skills
    section_feedback TEXT,       -- JSON object: {summary, keywords, skills, experience, format}
    improvement_suggestions TEXT, -- JSON array of prioritized suggestions
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Agent Architecture

There are five agents. Each has a single responsibility. They do not share state directly — they pass structured data through the database or as explicit function arguments.

### Agent 1: STAR Story Agent (`agents/star_agent.py`)

**Purpose:** Guide a user through building a STAR story for a single resume bullet.

**Inputs:**
- `bullet: str` — the original resume bullet
- `conversation_history: list[dict]` — prior turns in this session
- `user_message: str` — the user's latest message

**Outputs:**
- `response: str` — the agent's next conversational turn
- `extracted_star: dict | None` — `{situation, task, action, result}` when complete, else None

**Design note:** This agent is conversational by design. It does not ask four questions in sequence. It reads the conversation and decides what to probe next — sometimes asking about the result before the situation if the user has already revealed it. The system prompt instructs it to be natural, not fill-in-the-blank.

**When to write to DB:** Only when the user explicitly signals they are done (e.g. "that's good" / "save it"). Do not auto-save mid-conversation.

---

### Agent 2: Job Scraping Agent (`agents/job_scraping_agent.py`)

**Purpose:** Extract structured job details from a URL or raw text.

**Inputs:**
- `source: str` — a URL, raw JD text, or path to a PDF
- `source_type: Literal["url", "text", "pdf"]`

**Outputs:**
```python
{
  "company": str,
  "role": str,
  "role_type": str,           # e.g. "Product Manager", "Consultant"
  "description": str,
  "required_skills": list[str],
  "preferred_skills": list[str],
  "location": str | None,
  "scrape_success": bool,
  "fallback_needed": bool
}
```

**Design note:** Web scraping fails often. The agent must not raise an exception — it sets `scrape_success=False` and `fallback_needed=True` so the UI can prompt the user to paste the JD manually. This is a design decision worth explaining in interviews: fail gracefully, give the user a path forward.

---

### Agent 3: Resume Bullet Tailoring Agent (`agents/tailoring_agent.py`)

**Purpose:** Lead a back-and-forth conversation to rewrite a single bullet for a specific job posting.

**Inputs:**
- `bullet: str` — the original bullet
- `job_details: dict` — output from the Job Scraping Agent
- `story_bank: list[dict]` — completed STAR stories for this user
- `conversation_history: list[dict]`
- `user_message: str`

**Outputs:**
- `response: str` — agent's next turn
- `proposed_bullet: str | None` — when the agent proposes a rewrite
- `target_skill: str | None` — the skill this bullet demonstrates
- `is_finalized: bool` — True when user accepts the bullet

**Design note:** This agent is intentionally NOT one-shot. The system prompt instructs it to ask which skill the user wants to demonstrate before proposing a rewrite. It uses the story bank to ground proposals in real details — if a STAR story exists for the bullet, it references specific results from that story rather than making up numbers. This is the central architectural decision of the product.

**Custom resume agent plug-in point:** This is where the pre-built custom resume agent plugs in. Leave a clearly marked hook at the top of `tailoring_agent.py`:

```python
# HOOK: Custom resume agent
# When the custom agent is ready, import it here and route
# the rewrite step through it instead of the raw Anthropic call.
# The agent should accept (bullet, job_details, skill, story_context)
# and return a proposed bullet string.
USE_CUSTOM_RESUME_AGENT = False  # Flip to True when agent is ready
```

---

### Agent 4: Gmail Tracker Agent (`agents/gmail_agent.py`)

**Purpose:** Scan Gmail for application confirmation emails and extract structured job data.

**Inputs:**
- `gmail_service` — authenticated Gmail API service object
- `user_id: str` — the RecruitingEdge user ID
- `lookback_days: int = 7` — how far back to scan

**Outputs:**
- `list[dict]` — each item: `{company, role, date_applied, email_subject, email_id}`

**Design note:** The agent does not write to the DB directly. It returns a list of detected applications and lets the caller decide which ones to persist (avoiding duplicates). Deduplication logic lives in `db/database.py`, not in the agent.

---

### Agent 5: ATS Scoring Agent (`agents/ats_agent.py`)

**Purpose:** Simulate how an Applicant Tracking System would score a resume against a job description, returning structured, actionable feedback.

**Inputs:**
- `resume_text: str` — full extracted resume text
- `jd_text: str` — full job description text
- `application_id: str` — for writing results to DB

**Outputs:**
```python
{
  "overall_score": int,            # 0–100
  "keyword_score": int,            # 0–100: keyword frequency match
  "skills_score": int,             # 0–100: required skills coverage
  "experience_score": int,         # 0–100: seniority / title alignment
  "format_score": int,             # 0–100: ATS-parseable formatting signals
  "matched_keywords": list[str],
  "missing_keywords": list[str],
  "matched_skills": list[str],
  "missing_skills": list[str],
  "section_feedback": {
    "summary": str,
    "keywords": str,
    "skills": str,
    "experience": str,
    "format": str
  },
  "improvement_suggestions": list[str]  # prioritized, specific, actionable
}
```

**Design note:** Real ATS systems (Workday, Greenhouse, Lever) use keyword frequency, skills taxonomy matching, and title normalization — not full semantic understanding. This agent simulates that behavior deliberately: it is not trying to be smarter than an ATS, it is trying to replicate what one actually does so students can optimize accordingly. The system prompt should make this explicit. The agent produces a score, not a judgment. Improvement suggestions should be specific enough to act on (e.g. "Add 'cross-functional' — appears 3x in JD, 0x in resume" not "add more keywords").

---

## Build Order

Build in this sequence. Do not start the next phase until the current one is complete and manually tested.

### Phase 0: Project scaffold + database layer
- Create all directories and `__init__.py` files
- Write `db/schema.sql` with all six tables
- Write `db/database.py` with connection management and CRUD functions for every table
- Write `.env.example` with all required variables
- Write `requirements.txt`
- Write a smoke test in `tests/test_db.py` that creates all tables, inserts one row per table, reads it back, and deletes it

### Phase 1: STAR Story Builder
- `tools/pdf_parser.py` — resume PDF text extraction
- `agents/star_agent.py` — conversational STAR agent
- `pages/onboarding.py` — resume upload UI
- `pages/star_builder.py` — conversation UI + story bank view

### Phase 2: Job Posting Manager
- `tools/web_scraper.py` — URL scraping with fallback
- `agents/job_scraping_agent.py` — structured JD extraction
- `pages/job_manager.py` — add job UI + job card view

### Phase 3: Resume Bullet Tailoring Agent
- `agents/tailoring_agent.py` — conversational tailoring with custom agent hook
- `pages/tailoring.py` — side-by-side conversation UI

### Phase 4: ATS Scoring Agent
- `agents/ats_agent.py` — ATS simulation scoring
- `pages/ats_scorer.py` — score dashboard UI with category breakdown

### Phase 5: Gmail Application Tracker
- `tools/gmail_client.py` — OAuth setup + Gmail API client
- `agents/gmail_agent.py` — confirmation email detection
- `scheduler/gmail_scheduler.py` — APScheduler daily scan
- `pages/tracker.py` — Kanban board UI

### Phase 6: app.py + integration
- Wire all pages into Streamlit multi-page nav
- End-to-end test: upload resume → build STAR story → add job → tailor bullets → score against JD → check tracker

---

## Environment Variables

All secrets go in `.env`. Never commit `.env`.

```
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8501/oauth/callback
DATABASE_PATH=./recruitingedge.db
```

---

## Design Constraints

- **Never generate a formatted resume.** The app produces bullets only. No PDF, no DOCX resume output. Ever.
- **No school branding.** No Michigan/Ross references in UI copy, colors, or logos.
- **Fail gracefully.** Every external call (Anthropic, Gmail, scraper) must be wrapped in try/except. Users always get a clear message and a fallback path, never a stack trace.
- **Agents are stateless.** Agents do not store state internally. All state lives in the DB or is passed explicitly as arguments. This makes agents testable in isolation.
- **Clean separation.** `agents/` contains only agent logic. `tools/` contains only external integrations. `pages/` contains only Streamlit UI. `db/` contains only database code. Do not cross these boundaries.

---

## Code Style

- Type hints on all function signatures
- Docstrings on every agent function explaining inputs, outputs, and the design decision behind any non-obvious logic
- No magic strings — use constants or Literal types for status values, role types, source types
- Each agent file should begin with a module-level docstring explaining the agent's role, what it does NOT do, and how it hands off to the next agent

---

## Interview-Ready Design Decisions (document these in code comments)

1. **Why four agents instead of one?** Each agent has a different latency profile, failure mode, and retry strategy. The Gmail agent runs on a schedule; the STAR agent runs interactively; the scraping agent can fail silently. Combining them would make the failure surface unpredictable.

2. **Why is tailoring conversational?** One-shot rewrites produce polished-sounding but often factually thin bullets. The conversational loop forces the user to confirm which skill they want to demonstrate and verify that the rewrite reflects real experience — the Story Bank integration makes this possible.

3. **Why does the ATS agent simulate ATS behavior rather than use semantic similarity?** Real ATS systems are not LLMs. They do keyword frequency, skills taxonomy lookup, and title normalization. Optimizing for semantic similarity would give false confidence. The goal is to help students pass the actual filter, not to produce the most impressive-sounding resume.

4. **Why SQLite for v1?** Zero config, zero ops, ships with Python. The schema is fully normalized and PostgreSQL-compatible — the only change needed for v2 is the connection string and a `psycopg2` import swap.

5. **Why Streamlit?** The target user (Ross MBA student) will run this locally or on a shared Railway deployment. Streamlit removes all frontend build complexity and lets the focus stay on agent architecture.
