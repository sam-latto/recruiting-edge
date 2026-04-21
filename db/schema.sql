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
    matched_keywords TEXT,
    missing_keywords TEXT,
    matched_skills TEXT,
    missing_skills TEXT,
    section_feedback TEXT,
    improvement_suggestions TEXT,
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
