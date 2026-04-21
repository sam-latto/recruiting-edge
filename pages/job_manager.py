"""
Job Posting Manager page — add jobs and view the application pipeline.

Layout:
  Top    — Add Job form (URL / paste text / upload PDF, then extracted preview)
  Bottom — Job card grid showing all applications, grouped by status

Flow:
  1. User provides a job source (URL, pasted JD, or PDF)
  2. Agent extracts structured details and shows a preview for the user to confirm/edit
  3. User fills in date applied and clicks Save — record written to DB
  4. All saved jobs appear below as cards with status badges
"""

import uuid
from datetime import date

import streamlit as st

from agents.job_scraping_agent import run_job_scraping_agent
from db.database import (
    create_job_application,
    get_job_applications_for_user,
    update_job_application,
)
from pages.onboarding import require_user

# Valid pipeline statuses in display order
_STATUSES = ["applied", "phone_screen", "interview", "offer", "rejected", "withdrawn"]

_STATUS_LABELS = {
    "applied": "Applied",
    "phone_screen": "Phone Screen",
    "interview": "Interview",
    "offer": "Offer",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}

_STATUS_COLORS = {
    "applied": "blue",
    "phone_screen": "orange",
    "interview": "violet",
    "offer": "green",
    "rejected": "red",
    "withdrawn": "gray",
}


# ---------------------------------------------------------------------------
# Add Job section
# ---------------------------------------------------------------------------

def _render_add_job(user_id: str) -> None:
    st.subheader("Add a Job Posting")

    source_type = st.radio(
        "How do you want to add this job?",
        options=["URL", "Paste text", "Upload PDF"],
        horizontal=True,
    )

    source: str = ""
    pdf_bytes: bytes | None = None

    if source_type == "URL":
        source = st.text_input("Job posting URL", placeholder="https://...")
    elif source_type == "Paste text":
        source = st.text_area("Paste the job description", height=200)
    else:
        uploaded = st.file_uploader("Upload job description PDF", type=["pdf"])
        if uploaded:
            pdf_bytes = uploaded.read()

    extract_clicked = st.button("Extract job details", type="primary")

    if extract_clicked:
        if source_type == "URL" and not source.strip():
            st.error("Please enter a URL.")
            return
        if source_type == "Paste text" and not source.strip():
            st.error("Please paste the job description.")
            return
        if source_type == "Upload PDF" and pdf_bytes is None:
            st.error("Please upload a PDF.")
            return

        with st.spinner("Extracting job details…"):
            if source_type == "Upload PDF":
                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name
                result = run_job_scraping_agent(tmp_path, "pdf")
                os.unlink(tmp_path)
            elif source_type == "URL":
                result = run_job_scraping_agent(source.strip(), "url")
            else:
                result = run_job_scraping_agent(source.strip(), "text")

        if result["fallback_needed"]:
            st.warning(
                "Couldn't extract details automatically. "
                "Please paste the job description instead and try again."
            )
            return

        st.session_state["job_draft"] = result
        st.session_state["job_source_url"] = source.strip() if source_type == "URL" else ""
        st.session_state["job_raw_text"] = source.strip() if source_type == "Paste text" else ""
        st.rerun()

    # --- Preview + Save form ---
    draft = st.session_state.get("job_draft")
    if not draft:
        return

    st.divider()
    st.markdown("**Review and save**")
    st.caption("Edit any fields before saving.")

    with st.form("save_job_form"):
        company = st.text_input("Company", value=draft.get("company", ""))
        role = st.text_input("Role", value=draft.get("role", ""))
        location = st.text_input("Location", value=draft.get("location") or "")
        date_applied = st.date_input("Date applied", value=date.today())
        status = st.selectbox("Status", options=_STATUSES, format_func=lambda s: _STATUS_LABELS[s])
        notes = st.text_area("Notes (optional)", height=80)

        with st.expander("Job description preview"):
            st.write(draft.get("description", ""))
            req = draft.get("required_skills", [])
            pref = draft.get("preferred_skills", [])
            if req:
                st.markdown("**Required skills:** " + ", ".join(req))
            if pref:
                st.markdown("**Preferred skills:** " + ", ".join(pref))

        save_clicked = st.form_submit_button("Save to pipeline", type="primary")

    if save_clicked:
        if not company.strip() or not role.strip():
            st.error("Company and Role are required.")
            return

        app_id = str(uuid.uuid4())
        jd_text = draft.get("description", "")
        job_url = st.session_state.get("job_source_url", "")

        try:
            create_job_application(
                id=app_id,
                user_id=user_id,
                company=company.strip(),
                role=role.strip(),
                date_applied=str(date_applied),
                status=status,
                job_url=job_url or None,
                jd_text=jd_text or None,
                notes=notes.strip() or None,
                source="manual",
            )
        except Exception as e:
            st.error(f"Failed to save: {e}")
            return

        del st.session_state["job_draft"]
        st.session_state.pop("job_source_url", None)
        st.session_state.pop("job_raw_text", None)
        st.success(f"Saved — {company} / {role}")
        st.rerun()


# ---------------------------------------------------------------------------
# Job card grid
# ---------------------------------------------------------------------------

def _render_pipeline(user_id: str) -> None:
    st.subheader("Your Pipeline")

    apps = get_job_applications_for_user(user_id)
    if not apps:
        st.caption("No applications yet. Add your first job above.")
        return

    # Group by status
    grouped: dict[str, list] = {s: [] for s in _STATUSES}
    for app in apps:
        grouped.setdefault(app["status"], []).append(app)

    for status in _STATUSES:
        bucket = grouped.get(status, [])
        if not bucket:
            continue

        st.markdown(f"#### :{_STATUS_COLORS[status]}[{_STATUS_LABELS[status]}] ({len(bucket)})")
        cols = st.columns(min(len(bucket), 3))

        for i, app in enumerate(bucket):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{app['company']}**")
                    st.markdown(f"{app['role']}")
                    if app.get("date_applied"):
                        st.caption(f"Applied {app['date_applied']}")

                    new_status = st.selectbox(
                        "Status",
                        options=_STATUSES,
                        index=_STATUSES.index(app["status"]),
                        format_func=lambda s: _STATUS_LABELS[s],
                        key=f"status_{app['id']}",
                        label_visibility="collapsed",
                    )
                    if new_status != app["status"]:
                        update_job_application(app["id"], status=new_status)
                        st.rerun()

                    if app.get("notes"):
                        with st.expander("Notes"):
                            st.write(app["notes"])


# ---------------------------------------------------------------------------
# Page entrypoint
# ---------------------------------------------------------------------------

def render_page() -> None:
    if not require_user():
        return
    user_id = st.session_state["user_id"]
    _render_add_job(user_id)
    st.divider()
    _render_pipeline(user_id)


def main() -> None:
    st.set_page_config(page_title="Job Manager — RecruitingEdge", layout="wide")
    render_page()


if __name__ == "__main__":
    main()
