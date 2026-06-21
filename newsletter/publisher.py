import asyncio
import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_DATA_DIR = Path(__file__).parent.parent / "data"


def _truncate_sentences(text: str, n: int) -> str:
    """Return first n sentences.

    Split points (in priority order):
      - .  !  ?  followed by whitespace  (prose sentence boundary)
      - \\n\\n+                           (paragraph break)
      - \\n followed by a bullet char     (new bullet point)
    Single bare \\n is NOT a split point — Exa wraps long lines mid-sentence.
    """
    if not text:
        return ""
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}|\n(?=\s*[-•*])', text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    result = " ".join(parts[:n])
    if len(parts) > n:
        result += "..."
    return result


def render_html(newsletter: dict, meta: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    env.filters["truncate_sentences"] = _truncate_sentences
    template = env.get_template("newsletter.html")
    return template.render(newsletter=newsletter, meta=meta)


def generate_pdf(html: str) -> bytes:
    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf)
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} error(s)")
    return buf.getvalue()


async def _send_telegram_async(pdf_bytes: bytes, filename: str, caption: str, bot_token: str, chat_id: str) -> None:
    from telegram import Bot
    bot = Bot(token=bot_token)
    await bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=caption,
    )


def send_telegram(pdf_bytes: bytes, filename: str, caption: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[publisher] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping delivery")
        return
    asyncio.run(_send_telegram_async(pdf_bytes, filename, caption, bot_token, chat_id))


def run_publisher(newsletter: dict, run_id: str, name: str, cost_usd: float) -> Path:
    _DATA_DIR.mkdir(exist_ok=True)

    meta = {
        "article_count": len(newsletter.get("sections", [])),
        "paper_count":   len(newsletter.get("papers", [])),
        "tweet_count":   len(newsletter.get("tweets", [])),
        "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "cost_usd":      cost_usd,
        "run_id":        run_id,
    }

    print("[publisher] Rendering HTML...")
    html = render_html(newsletter, meta)

    print("[publisher] Generating PDF...")
    pdf_bytes = generate_pdf(html)

    filename = f"newsletter-{name}.pdf"
    pdf_path = _DATA_DIR / filename
    pdf_path.write_bytes(pdf_bytes)
    print(f"[publisher] PDF saved to {pdf_path}")

    caption = (
        f"Research Newsletter — {newsletter.get('newsletter_date', 'today')}\n"
        f"{meta['article_count']} articles | Cost: ${cost_usd:.4f}"
    )
    print("[publisher] Sending via Telegram...")
    send_telegram(pdf_bytes, filename, caption)

    return pdf_path
