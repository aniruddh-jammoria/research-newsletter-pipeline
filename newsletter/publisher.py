import asyncio
import io
import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_DATA_DIR = Path(__file__).parent.parent / "data"

# Telegram limits: 1024 characters on a media caption, 4096 on a text message.
# Five bullets at the length prompts/overview.md allows can exceed the caption
# limit, which would fail the send outright — so the overview moves to its own
# message when it does not fit rather than being cut off or lost.
_CAPTION_LIMIT = 1024
_MESSAGE_LIMIT = 4096


def _build_message(newsletter: dict, meta: dict, cost_usd: float) -> tuple[str, str | None]:
    """Return (caption for the PDF, optional follow-up message).

    The overview rides in the caption whenever it fits, so the summary and the
    file arrive as one notification.
    """
    header = (
        f"Research Newsletter — {newsletter.get('newsletter_date', 'today')}\n"
        f"{meta['article_count']} articles | Cost: ${cost_usd:.4f}"
    )

    bullets = [b.strip() for b in (newsletter.get("overview") or []) if b and b.strip()]
    if not bullets:
        return header, None

    overview = "\n\n".join(f"• {b}" for b in bullets)
    combined = f"{header}\n\n{overview}"
    if len(combined) <= _CAPTION_LIMIT:
        return combined, None

    return header, overview[:_MESSAGE_LIMIT]


def render_html(newsletter: dict, meta: dict) -> str:
    # Nothing is truncated at render time any more: articles and papers are
    # written to a fixed 100-150 words, tweets to 50-100, so everything the
    # template receives is already the right length to print in full.
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("newsletter.html")
    return template.render(newsletter=newsletter, meta=meta)


def generate_pdf(html: str) -> bytes:
    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf)
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} error(s)")
    return buf.getvalue()


async def _send_telegram_async(
    pdf_bytes: bytes,
    filename: str,
    caption: str,
    bot_token: str,
    chat_id: str,
    follow_up: str | None = None,
) -> None:
    from telegram import Bot
    bot = Bot(token=bot_token)
    await bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=caption,
    )
    if follow_up:
        await bot.send_message(chat_id=chat_id, text=follow_up)


def send_telegram(pdf_bytes: bytes, filename: str, caption: str, follow_up: str | None = None) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[publisher] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping delivery")
        return
    asyncio.run(_send_telegram_async(pdf_bytes, filename, caption, bot_token, chat_id, follow_up))


def run_publisher(newsletter: dict, run_id: str, output_name: str, cost_usd: float) -> Path:
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

    filename = f"{output_name}.pdf"
    pdf_path = _DATA_DIR / filename
    pdf_path.write_bytes(pdf_bytes)
    print(f"[publisher] PDF saved to {pdf_path}")

    caption, follow_up = _build_message(newsletter, meta, cost_usd)
    bullets = len(newsletter.get("overview") or [])
    where = "separate message" if follow_up else "caption"
    print(f"[publisher] Sending via Telegram ({bullets} overview bullet(s) in the {where})...")
    send_telegram(pdf_bytes, filename, caption, follow_up)

    return pdf_path
