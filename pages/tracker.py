"""
Application Tracker page — Kanban board UI for managing the job pipeline.

Layout:
  Top    — Gmail integration panel (connect, scan now, last scan status)
  Bottom — Kanban columns: Applied | Phone Screen | Interview | Offer | Rejected | Withdrawn

Gmail flow:
  - If credentials.json exists, user can connect Gmail and trigger a scan
  - Detected applications are shown as a diff (new vs. already tracked) before saving
  - The daily background scanner runs independently; this page just shows results

Kanban:
  - Each card shows company, role, date applied, source badge (manual vs gmail)
  - Cards have an inline status dropdown that updates the DB immediately
  - Notes are shown in a collapsible expander on each card
"""

import streamlit as st

from db.database import (
    get_job_applications_for_user,
    update_job_application,
)
from pages.onboarding import require_user

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
# Gmail integration panel
# ---------------------------------------------------------------------------

def _render_gmail_panel(user_id: str) -> None:
    st.subheader("Gmail Integration")

    from pathlib import Path
    credentials_present = Path("credentials.json").exists()

    if not credentials_present:
        st.info(
            "To auto-detect applications from Gmail, add `credentials.json` "
            "to the project root (downloaded from Google Cloud Console → "
            "APIs & Services → Credentials → OAuth 2.0 Client IDs)."
        )
        return

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("Scan Gmail now", type="primary"):
            with st.spinner("Connecting to Gmail and scanning the last 30 days…"):
                try:
                    from tools.gmail_client import get_gmail_service
                    from scheduler.gmail_scheduler import run_scan_now
                    service = get_gmail_service()
                    saved = run_scan_now(service, user_id)
                    if saved:
                        st.success(f"Found and saved {saved} new application(s).")
                    else:
                        st.info("No new applications detected in the last 30 days.")
                    st.rerun()
                except FileNotFoundError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Gmail scan failed: {e}")

    with col2:
        st.caption(
            "Scans for subject lines containing: 'application received', "
            "'thank you for applying', 'application submitted', and similar."
        )


# ---------------------------------------------------------------------------
# Kanban board
# ---------------------------------------------------------------------------

def _render_kanban(user_id: str) -> None:
    st.subheader("Pipeline")

    apps = get_job_applications_for_user(user_id)
    if not apps:
        st.caption("No applications yet. Add one in the Job Manager or scan Gmail above.")
        return

    # Group by status
    grouped: dict[str, list] = {s: [] for s in _STATUSES}
    for app in apps:
        status = app["status"] if app["status"] in _STATUSES else "applied"
        grouped[status].append(app)

    # Render one column per status (show all statuses even if empty)
    cols = st.columns(len(_STATUSES))

    for col, status in zip(cols, _STATUSES):
        bucket = grouped[status]
        color = _STATUS_COLORS[status]
        label = _STATUS_LABELS[status]

        with col:
            st.markdown(f"**:{color}[{label}]**")
            st.caption(f"{len(bucket)} application{'s' if len(bucket) != 1 else ''}")

            for app in bucket:
                with st.container(border=True):
                    # Source badge
                    source = app.get("source", "manual")
                    badge = ":gray[gmail]" if source == "gmail" else ":blue[manual]"
                    st.markdown(f"{badge}")

                    st.markdown(f"**{app['company']}**")
                    st.markdown(f"*{app['role']}*")

                    if app.get("date_applied"):
                        st.caption(app["date_applied"])

                    # Inline status update
                    new_status = st.selectbox(
                        "Move to",
                        options=_STATUSES,
                        index=_STATUSES.index(status),
                        format_func=lambda s: _STATUS_LABELS[s],
                        key=f"kanban_status_{app['id']}",
                        label_visibility="collapsed",
                    )
                    if new_status != status:
                        update_job_application(app["id"], status=new_status)
                        st.rerun()

                    if app.get("notes"):
                        with st.expander("Notes"):
                            st.write(app["notes"])

                    if app.get("next_steps"):
                        with st.expander("Next steps"):
                            st.write(app["next_steps"])


# ---------------------------------------------------------------------------
# Page entrypoint
# ---------------------------------------------------------------------------

def render_page() -> None:
    if not require_user():
        return
    user_id = st.session_state["user_id"]
    st.title("Application Tracker")
    _render_gmail_panel(user_id)
    st.divider()
    _render_kanban(user_id)


def main() -> None:
    st.set_page_config(
        page_title="Application Tracker — RecruitingEdge",
        layout="wide",
    )
    render_page()


if __name__ == "__main__":
    main()
