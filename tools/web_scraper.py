"""
Web scraping utility using BeautifulSoup + Requests.

Fetches the visible text from a job posting URL. Returns an empty string on
any failure — callers must check the return value and set fallback_needed=True
rather than letting exceptions propagate to the UI.

Does NOT: parse structure or extract fields. That is the job scraping agent's job.
"""

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = 10  # seconds
_MAX_CHARS = 20_000  # trim very long pages before sending to the LLM


def scrape_url(url: str) -> tuple[str, bool]:
    """
    Fetch and extract visible text from a URL.

    Returns:
        (text, success) where text is the page body and success is False if
        anything went wrong (network error, non-200 status, parse failure).
    """
    try:
        response = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if response.status_code != 200:
            return "", False

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove boilerplate elements that add noise without content
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Collapse runs of blank lines
        lines = [ln for ln in text.splitlines() if ln.strip()]
        cleaned = "\n".join(lines)
        return cleaned[:_MAX_CHARS], True

    except Exception:
        return "", False
