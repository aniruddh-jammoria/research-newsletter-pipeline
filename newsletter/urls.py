"""URL identity helpers for the pre-LLM deduplication step.

Two results can point at the same document under different URLs, which the
plain string comparison in the search modules cannot see. arXiv is the worst
offender: it serves one paper at /abs/, /html/ and /pdf/, with or without a
version suffix, so a single paper can be fetched, summarized and printed more
than once. That is a mechanical problem with a mechanical fix — no LLM needed.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that never change which document a URL refers to. Kept
# deliberately narrow: params like `ref` or `source` are meaningful on some
# sites, so merging on them risks collapsing genuinely different pages.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "igshid", "mc_cid", "mc_eid", "_hsenc", "_hsmi",
}

# 2607.19941 / 2607.19941v2 — the modern identifier
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
# cs/0501001, math.GT/0309136 — the pre-2007 identifier
_ARXIV_OLD = re.compile(r"([a-zA-Z-]+(?:\.[A-Za-z]{2})?/\d{7})(?:v\d+)?")


def _host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def arxiv_id(url: str) -> str | None:
    """Return the version-less arXiv identifier for a URL, or None.

    The version is deliberately stripped: /html/2607.19941v1 and
    /pdf/2607.19941 are the same paper, and that exact pair is what produced a
    duplicated entry in a real run.
    """
    host = _host(url)
    if host != "arxiv.org" and not host.endswith(".arxiv.org"):
        return None

    path = urlsplit(url).path
    if path.lower().endswith(".pdf"):
        path = path[:-4]

    match = _ARXIV_NEW.search(path)
    if match:
        return match.group(1)
    match = _ARXIV_OLD.search(path)
    if match:
        return match.group(1).lower()
    return None


def canonical_key(url: str) -> str:
    """A stable identity for `url`, for use as a deduplication key.

    arXiv URLs collapse to their identifier. Everything else is normalized
    conservatively: lowercased host without `www.`, no trailing slash, no
    fragment, and tracking parameters removed. The scheme is dropped so http
    and https forms of one page match.
    """
    paper = arxiv_id(url)
    if paper:
        return f"arxiv:{paper}"

    parts = urlsplit(url)
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ])
    return urlunsplit(("", _host(url), parts.path.rstrip("/").lower() or "/", query, ""))


def display_url(url: str) -> str:
    """The URL to link to in the newsletter.

    arXiv results arrive as a mix of /abs/, /html/ and /pdf/ links. Point them
    all at /abs/, which is the landing page a reader wants: abstract first,
    with links to both the HTML and PDF renderings. Other URLs pass through
    unchanged.
    """
    paper = arxiv_id(url)
    return f"https://arxiv.org/abs/{paper}" if paper else url
