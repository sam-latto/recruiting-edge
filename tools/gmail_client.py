"""
Gmail API client — OAuth 2.0 setup and authenticated service builder.

Handles the full OAuth flow: if a token.json exists and is valid it reuses it;
if it is expired it refreshes it; if no token exists it runs the browser-based
consent flow and writes a new token.json.

Does NOT: read emails, parse content, or interact with the database. Those
responsibilities belong to gmail_agent.py and db/database.py respectively.

token.json is excluded from git via .gitignore. credentials.json (downloaded
from Google Cloud Console) must be present in the project root.
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Read-only scope — never request broader permissions than needed
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_TOKEN_PATH = Path("token.json")
_CREDENTIALS_PATH = Path("credentials.json")


def get_gmail_service():
    """
    Build and return an authenticated Gmail API service object.

    On first run this opens a browser window for OAuth consent and writes
    token.json. Subsequent calls reuse or silently refresh the saved token.

    Raises:
        FileNotFoundError: if credentials.json is missing.
        Exception: if the OAuth flow or API build fails.
    """
    if not _CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            "credentials.json not found. Download it from Google Cloud Console "
            "(APIs & Services → Credentials → OAuth 2.0 Client IDs) and place "
            "it in the project root."
        )

    creds: Credentials | None = None

    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_PATH), _SCOPES
            )
            creds = flow.run_local_server(port=0)
        _TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_messages(
    service,
    query: str,
    max_results: int = 50,
) -> list[dict]:
    """
    Fetch a list of message metadata dicts matching a Gmail search query.

    Returns an empty list on any API error rather than raising — the caller
    decides how to surface the failure.

    Args:
        service: Authenticated Gmail API service from get_gmail_service().
        query: Gmail search string (e.g. 'subject:application after:2024/01/01').
        max_results: Cap on number of messages returned.

    Returns:
        List of dicts with keys: id, threadId, subject, from, date, snippet.
    """
    try:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        raw_messages = response.get("messages", [])
    except HttpError:
        return []

    results = []
    for msg_ref in raw_messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata",
                     metadataHeaders=["Subject", "From", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            results.append({
                "id": msg["id"],
                "threadId": msg.get("threadId"),
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            })
        except HttpError:
            continue  # skip individual message failures, keep scanning

    return results
