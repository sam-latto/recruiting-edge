"""
STAR Story Builder page — conversation UI and story bank view.

Layout:
  Left column  — chat interface with the STAR agent for the active bullet
  Right column — story bank (all completed stories for this user)

Flow:
  1. User types a resume bullet they want to develop
  2. Agent asks natural follow-up questions to draw out Situation/Task/Action/Result
  3. When the user signals completion ("save it", "done", etc.) the agent calls
     submit_star_story and the UI shows a Save button
  4. Saved stories appear in the story bank and are later available to the
     tailoring agent
"""

import uuid

import streamlit as st

from agents.star_agent import run_star_agent
from db.database import (
    create_star_story,
    get_star_stories_for_user,
    update_star_story,
)
from pages.onboarding import require_user

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _reset_conversation() -> None:
    st.session_state["star_bullet"] = ""
    st.session_state["star_history"] = []
    st.session_state["star_pending"] = None  # extracted STAR dict awaiting save


def _init_state() -> None:
    if "star_bullet" not in st.session_state:
        _reset_conversation()


# ---------------------------------------------------------------------------
# Sub-components
# ---------------------------------------------------------------------------

def _render_story_bank(user_id: str) -> None:
    st.subheader("Story Bank")
    stories = get_star_stories_for_user(user_id)
    complete = [s for s in stories if s["is_complete"]]
    in_progress = [s for s in stories if not s["is_complete"]]

    if not stories:
        st.caption("No stories yet. Start a conversation on the left.")
        return

    if complete:
        st.markdown("**Completed**")
        for s in complete:
            with st.expander(s["original_bullet"][:80] + ("…" if len(s["original_bullet"]) > 80 else "")):
                st.markdown(f"**Situation:** {s['situation'] or '—'}")
                st.markdown(f"**Task:** {s['task'] or '—'}")
                st.markdown(f"**Action:** {s['action'] or '—'}")
                st.markdown(f"**Result:** {s['result'] or '—'}")

    if in_progress:
        st.markdown("**In Progress**")
        for s in in_progress:
            with st.expander(s["original_bullet"][:80] + ("…" if len(s["original_bullet"]) > 80 else "")):
                st.caption("Not yet saved as complete.")
                if st.button("Resume", key=f"resume_{s['id']}"):
                    st.session_state["star_bullet"] = s["original_bullet"]
                    st.session_state["star_history"] = []
                    st.session_state["star_pending"] = None
                    st.rerun()


def _render_chat(user_id: str) -> None:
    st.subheader("Build a STAR Story")

    bullet = st.session_state["star_bullet"]

    # --- Bullet input (shown only when no active conversation) ---
    if not bullet:
        new_bullet = st.text_area(
            "Paste a resume bullet to develop",
            placeholder="e.g. Led cross-functional team to launch mobile payment feature...",
            height=80,
        )
        if st.button("Start", type="primary") and new_bullet.strip():
            st.session_state["star_bullet"] = new_bullet.strip()

            # Create an in-progress DB record so the story bank shows it immediately
            story_id = str(uuid.uuid4())
            create_star_story(story_id, user_id, new_bullet.strip())
            st.session_state["star_story_id"] = story_id
            st.rerun()
        return

    st.caption(f"**Bullet:** {bullet}")

    # --- Conversation history ---
    for msg in st.session_state["star_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Pending save banner ---
    pending = st.session_state.get("star_pending")
    if pending:
        st.success("Your STAR story is ready to save.")
        with st.expander("Preview"):
            st.markdown(f"**Situation:** {pending['situation']}")
            st.markdown(f"**Task:** {pending['task']}")
            st.markdown(f"**Action:** {pending['action']}")
            st.markdown(f"**Result:** {pending['result']}")

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Save Story", type="primary"):
                story_id = st.session_state.get("star_story_id", str(uuid.uuid4()))
                try:
                    update_star_story(
                        story_id,
                        situation=pending["situation"],
                        task=pending["task"],
                        action=pending["action"],
                        result=pending["result"],
                        is_complete=True,
                    )
                    st.success("Saved to your story bank!")
                    _reset_conversation()
                    if "star_story_id" in st.session_state:
                        del st.session_state["star_story_id"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        with col2:
            if st.button("Keep editing"):
                st.session_state["star_pending"] = None
                st.rerun()
        return

    # --- Chat input ---
    user_input = st.chat_input("Your response…")
    if user_input:
        st.session_state["star_history"].append({"role": "user", "content": user_input})

        with st.spinner("Thinking…"):
            response, extracted = run_star_agent(
                bullet=bullet,
                conversation_history=st.session_state["star_history"][:-1],
                user_message=user_input,
            )

        st.session_state["star_history"].append({"role": "assistant", "content": response})

        if extracted:
            st.session_state["star_pending"] = extracted

        st.rerun()

    # --- Reset button ---
    if st.button("Start over with a different bullet"):
        _reset_conversation()
        if "star_story_id" in st.session_state:
            del st.session_state["star_story_id"]
        st.rerun()


# ---------------------------------------------------------------------------
# Page entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="STAR Story Builder — RecruitingEdge", layout="wide")

    if not require_user():
        return

    _init_state()

    user_id = st.session_state["user_id"]

    left, right = st.columns([2, 1])
    with left:
        _render_chat(user_id)
    with right:
        _render_story_bank(user_id)


if __name__ == "__main__":
    main()
