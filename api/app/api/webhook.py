"""Webhook endpoints — WhatsApp Business API, Telegram Bot API + generic webhook.

WhatsApp Cloud API flow:
1. Meta sends GET  /webhook/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
2. We verify and return the challenge.
3. Meta sends POST /webhook/whatsapp with message payloads.
4. We extract the text, run a research job, and send back results.

Telegram Bot API flow:
1. Set webhook via https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL>/webhook/telegram
2. Telegram sends POST /webhook/telegram with Update JSON.
3. We extract the text, run a research job, and send back results.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html as _html
import io
import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from app.core import config
from app.core.jobs import create_job, get_job
from app.models.api import JobResult, JobStatus, WebhookEvent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhook"])

# Human-readable status labels
_STATUS_EMOJI: dict[JobStatus, str] = {
    JobStatus.PENDING: "⏳",
    JobStatus.SEARCHING: "🔍 Searching the web…",
    JobStatus.SYNTHESISING: "🧠 Synthesising evidence…",
    JobStatus.REPORTING: "📝 Writing report…",
    JobStatus.EVALUATING: "✅ Evaluating quality…",
    JobStatus.COMPLETED: "✅ Done!",
    JobStatus.FAILED: "❌ Something went wrong",
}

# WhatsApp max message body length
_WA_MAX_LEN = 4096


# ── WhatsApp helpers ─────────────────────────────────────────────────────────

def _send_whatsapp_message(to: str, text: str) -> None:
    """Send a single text message via WhatsApp Cloud API."""
    if not config.WHATSAPP_TOKEN or not config.WHATSAPP_PHONE_ID:
        logger.warning("WhatsApp not configured — skipping send to %s", to)
        return

    url = f"https://graph.facebook.com/v18.0/{config.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:_WA_MAX_LEN]},
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        logger.info("WhatsApp message sent to %s", to)
    except Exception as exc:
        logger.error("Failed to send WhatsApp message: %s", exc)


def _send_whatsapp_chunked(to: str, text: str) -> None:
    """Send a long message as multiple WhatsApp messages, splitting on paragraph boundaries."""
    if len(text) <= _WA_MAX_LEN:
        _send_whatsapp_message(to, text)
        return

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > _WA_MAX_LEN:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds the limit, hard-wrap it
            if len(paragraph) > _WA_MAX_LEN:
                for i in range(0, len(paragraph), _WA_MAX_LEN):
                    chunks.append(paragraph[i : i + _WA_MAX_LEN])
                current = ""
            else:
                current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)

    total = len(chunks)
    for idx, chunk in enumerate(chunks, 1):
        header = f"[{idx}/{total}]\n\n" if total > 1 else ""
        _send_whatsapp_message(to, header + chunk)


def _extract_whatsapp_message(body: dict) -> tuple[str, str] | None:
    """Extract (sender_phone, text) from a WhatsApp webhook payload.

    Returns None if not a text message.
    """
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        message = value["messages"][0]
        if message["type"] != "text":
            return None
        sender = message["from"]
        text = message["text"]["body"]
        return sender, text
    except (KeyError, IndexError):
        return None


# ── WhatsApp delivery callbacks ──────────────────────────────────────────────

def _make_progress_callback(sender: str):
    """Return a callback that sends stage updates to the WhatsApp user."""
    def on_progress(job_id: str, status: JobStatus) -> None:
        label = _STATUS_EMOJI.get(status, str(status.value))
        # Only send for the main stage transitions, not COMPLETED/FAILED (handled by on_complete)
        if status in (JobStatus.SEARCHING, JobStatus.SYNTHESISING, JobStatus.REPORTING, JobStatus.EVALUATING):
            _send_whatsapp_message(sender, label)
    return on_progress


def _make_complete_callback(sender: str):
    """Return a callback that delivers the final report (or error) to the WhatsApp user."""
    def on_complete(job_id: str, job: JobResult) -> None:
        if job.status == JobStatus.FAILED:
            _send_whatsapp_message(
                sender,
                f"❌ Research failed.\n\nError: {job.error[:500]}\n\n"
                f"Please try again or rephrase your question.",
            )
            return

        # Build a summary header
        scores = ""
        if job.evaluation:
            scores = (
                f"\n📊 Quality scores:\n"
                f"  • Coverage: {job.evaluation.coverage:.0%}\n"
                f"  • Faithfulness: {job.evaluation.faithfulness:.0%}\n"
                f"  • Usefulness: {job.evaluation.usefulness:.0%}\n"
                f"  • Hallucination risk: {job.evaluation.hallucination_rate:.0%}"
            )

        header = (
            f"✅ Research complete!\n\n"
            f"📚 {job.sources_count} sources · {job.evidence_count} evidence pieces · {job.themes_count} themes"
            f"{scores}\n\n"
            f"─── Report ───\n\n"
        )

        _send_whatsapp_chunked(sender, header + job.report)

    return on_complete


# ── WhatsApp webhook endpoints ───────────────────────────────────────────────

@router.get("/whatsapp")
def whatsapp_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Verification endpoint for Meta webhook setup."""
    if hub_mode == "subscribe" and hub_verify_token == config.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified")
        return int(hub_challenge) if hub_challenge else ""
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def whatsapp_inbound(request: Request):
    """Receive inbound WhatsApp messages and start research jobs."""
    # Verify Meta signature if WEBHOOK_SECRET is configured
    if config.WEBHOOK_SECRET:
        signature = request.headers.get("x-hub-signature-256", "")
        body_bytes = await request.body()
        expected = "sha256=" + hmac.new(
            config.WEBHOOK_SECRET.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
        body = __import__("json").loads(body_bytes)
    else:
        body = await request.json()

    result = _extract_whatsapp_message(body)
    if result is None:
        return {"status": "ignored"}

    sender, text = result
    logger.info("WhatsApp message from %s: %s", sender, text[:80])

    # Create a background research job with WhatsApp delivery callbacks
    job = create_job(
        text,
        on_progress=_make_progress_callback(sender),
        on_complete=_make_complete_callback(sender),
    )

    # Send acknowledgement
    _send_whatsapp_message(
        sender,
        f"🔍 Research started!\n\n"
        f"Question: {text[:200]}\n"
        f"Job ID: {job.job_id}\n\n"
        f"I'll send you progress updates and the full report when it's ready.",
    )

    return {"status": "accepted", "job_id": job.job_id}


# ── Generic webhook endpoint ────────────────────────────────────────────────

# ── Telegram helpers ─────────────────────────────────────────────────────────

# Telegram max message length
_TG_MAX_LEN = 4096

# ── Markdown → Telegram HTML conversion ──────────────────────────────────────

_FENCE_RE = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _prose_to_html(text: str) -> str:
    """Convert a prose Markdown section (no fenced blocks) to Telegram HTML.

    Steps: save inline code → escape HTML special chars → apply formatting.
    """
    # Save inline code to avoid double-escaping its content
    saved_inline: list[str] = []

    def save_inline(m: re.Match) -> str:
        saved_inline.append(_html.escape(m.group(1)))
        return f"\x00IC{len(saved_inline) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", save_inline, text)

    # Strip any remaining HTML tags from the source
    text = re.sub(r"<[^>]+>", "", text)

    # Escape HTML special chars in plain text
    text = _html.escape(text, quote=False)

    # Headings → bold lines
    def fmt_heading(m: re.Match) -> str:
        level = len(m.group(1))
        title = m.group(2).strip()
        return f"\n<b>━━ {title.upper()} ━━</b>\n" if level <= 2 else f"\n<b>▸ {title}</b>"

    text = _HEADING_RE.sub(fmt_heading, text)

    # Bold, italic
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)

    # Images → label only
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "🖼", text)

    # Links → clickable
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Restore inline code
    for i, code in enumerate(saved_inline):
        text = text.replace(f"\x00IC{i}\x00", f"<code>{code}</code>")

    return text


def _markdown_to_telegram_html(md: str) -> tuple[str, list[str]]:
    """Convert a Markdown report to Telegram HTML + a list of Mermaid diagram strings.

    Returns (html_text, mermaid_codes) where each mermaid_code can be rendered
    as an image via mermaid.ink.
    """
    mermaid_codes: list[str] = []
    parts: list[str] = []
    last_end = 0

    for m in _FENCE_RE.finditer(md):
        # Convert prose before this fence
        if m.start() > last_end:
            parts.append(_prose_to_html(md[last_end:m.start()]))

        lang = m.group(1).strip().lower()
        content = m.group(2)

        if lang == "mermaid":
            mermaid_codes.append(content.strip())
            # Placeholder so surrounding text doesn't merge
            parts.append("")
        else:
            parts.append(f"<pre><code>{_html.escape(content.rstrip())}</code></pre>")

        last_end = m.end()

    if last_end < len(md):
        parts.append(_prose_to_html(md[last_end:]))

    result = "\n".join(p for p in parts if p.strip())
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result, mermaid_codes


def _mermaid_to_photo_url(mermaid_code: str) -> str:
    """Return a mermaid.ink URL that renders the diagram as a PNG image."""
    encoded = base64.urlsafe_b64encode(mermaid_code.encode("utf-8")).decode("ascii")
    return f"https://mermaid.ink/img/{encoded}"


def _send_telegram_message(chat_id: int | str, text: str, parse_mode: str | None = None) -> int | None:
    """Send a single text message via Telegram Bot API. Returns the message_id on success."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram not configured — skipping send to %s", chat_id)
        return None

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": text[:_TG_MAX_LEN],
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        logger.info("Telegram message sent to %s", chat_id)
        return resp.json().get("result", {}).get("message_id")
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return None


def _edit_telegram_message(chat_id: int | str, message_id: int, text: str) -> None:
    """Edit an existing Telegram message in-place."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/editMessageText"
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:_TG_MAX_LEN],
            })
    except Exception as exc:
        logger.error("Failed to edit Telegram message: %s", exc)


def _send_telegram_chat_action(chat_id: int | str, action: str = "typing") -> None:
    """Send a chat action (e.g. 'typing') to show activity in Telegram."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendChatAction"
    try:
        with httpx.Client(timeout=5) as client:
            client.post(url, json={"chat_id": chat_id, "action": action})
    except Exception as exc:
        logger.error("Failed to send chat action: %s", exc)


def _send_telegram_document(chat_id: int | str, filename: str, data: bytes, caption: str = "") -> None:
    """Send a file (e.g. PDF) to a Telegram chat via sendDocument."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                data={"chat_id": str(chat_id), "caption": caption[:1024]},
                files={"document": (filename, io.BytesIO(data), "application/pdf")},
            )
            resp.raise_for_status()
        logger.info("Telegram document sent to %s: %s", chat_id, filename)
    except Exception as exc:
        logger.error("Failed to send Telegram document: %s", exc)


def _send_telegram_photo(chat_id: int | str, photo_url: str, caption: str = "") -> None:
    """Send an image URL as a Telegram photo message."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json={
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": caption[:1024],
            })
            resp.raise_for_status()
        logger.info("Telegram photo sent to %s", chat_id)
    except Exception as exc:
        logger.error("Failed to send Telegram photo: %s", exc)


def _send_telegram_chunked(chat_id: int | str, text: str, parse_mode: str | None = None) -> None:
    """Send a long message as multiple Telegram messages, splitting on paragraph boundaries."""
    if len(text) <= _TG_MAX_LEN:
        _send_telegram_message(chat_id, text, parse_mode=parse_mode)
        return

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > _TG_MAX_LEN:
            if current:
                chunks.append(current)
            if len(paragraph) > _TG_MAX_LEN:
                for i in range(0, len(paragraph), _TG_MAX_LEN):
                    chunks.append(paragraph[i : i + _TG_MAX_LEN])
                current = ""
            else:
                current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)

    total = len(chunks)
    for idx, chunk in enumerate(chunks, 1):
        header = f"[{idx}/{total}]\n\n" if total > 1 else ""
        _send_telegram_message(chat_id, header + chunk, parse_mode=parse_mode)


def _extract_telegram_message(body: dict) -> tuple[int, str] | None:
    """Extract (chat_id, text) from a Telegram Update payload.

    Returns None if not a text message.
    """
    try:
        message = body.get("message") or body.get("edited_message")
        if not message or "text" not in message:
            return None
        chat_id = message["chat"]["id"]
        text = message["text"]
        return chat_id, text
    except (KeyError, TypeError):
        return None


def _extract_telegram_voice(body: dict) -> tuple[int, str] | None:
    """Extract (chat_id, file_id) from a Telegram Update containing a voice message.

    Returns None if not a voice message.
    """
    try:
        message = body.get("message") or body.get("edited_message")
        if not message or "voice" not in message:
            return None
        chat_id = message["chat"]["id"]
        file_id = message["voice"]["file_id"]
        return chat_id, file_id
    except (KeyError, TypeError):
        return None


def _download_telegram_voice(file_id: str) -> bytes | None:
    """Download a voice message audio file from Telegram.

    Calls getFile to resolve the path, then downloads the raw OGG bytes.
    Returns None on any failure.
    """
    if not config.TELEGRAM_BOT_TOKEN:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            r.raise_for_status()
            file_path = r.json()["result"]["file_path"]

            audio = client.get(
                f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{file_path}"
            )
            audio.raise_for_status()
            return audio.content
    except Exception as exc:
        logger.error("Failed to download Telegram voice file: %s", exc)
        return None


def _transcribe_voice(audio_bytes: bytes) -> str | None:
    """Transcribe audio bytes using Groq Whisper (whisper-large-v3).

    Returns the transcribed text, or None on failure.
    """
    if not config.GROQ_API_KEY:
        logger.error("GROQ_API_KEY not set — cannot transcribe voice")
        return None
    try:
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=("voice.ogg", audio_bytes, "audio/ogg"),
        )
        text = transcription.text.strip()
        logger.info("Voice transcribed: %s", text[:120])
        return text
    except Exception as exc:
        logger.error("Groq Whisper transcription failed: %s", exc)
        return None


# ── Telegram delivery callbacks ──────────────────────────────────────────────

_PROGRESS_STEPS: dict[JobStatus, str] = {
    JobStatus.SEARCHING:    "🔍 Searching the web…\n⬜⬜⬜⬜ Step 1/4",
    JobStatus.SYNTHESISING: "🧠 Synthesising evidence…\n🟩⬜⬜⬜ Step 2/4",
    JobStatus.REPORTING:    "📝 Writing report…\n🟩🟩⬜⬜ Step 3/4",
    JobStatus.EVALUATING:   "✅ Evaluating quality…\n🟩🟩🟩⬜ Step 4/4",
}


def _make_telegram_progress_callback(chat_id: int | str, status_message_id: int | None):
    """Return a callback that edits a single status message at each stage."""
    _msg_id: list[int | None] = [status_message_id]

    def on_progress(job_id: str, status: JobStatus) -> None:
        label = _PROGRESS_STEPS.get(status)
        if not label:
            return
        if _msg_id[0]:
            _edit_telegram_message(chat_id, _msg_id[0], label)
        else:
            _msg_id[0] = _send_telegram_message(chat_id, label)
    return on_progress


def _make_telegram_complete_callback(chat_id: int | str, status_message_id: int | None, question: str):
    """Return a callback that delivers the final report (and PDF) to the Telegram user."""
    _msg_id: list[int | None] = [status_message_id]

    def on_complete(job_id: str, job: JobResult) -> None:
        if job.status == JobStatus.FAILED:
            msg = (
                f"❌ Research failed.\n\nError: {job.error[:500]}\n\n"
                f"Please try again or rephrase your question."
            )
            if _msg_id[0]:
                _edit_telegram_message(chat_id, _msg_id[0], msg)
            else:
                _send_telegram_message(chat_id, msg)
            return

        scores = ""
        if job.evaluation:
            scores = (
                f"\n📊 Quality scores:\n"
                f"  • Coverage: {job.evaluation.coverage:.0%}\n"
                f"  • Faithfulness: {job.evaluation.faithfulness:.0%}\n"
                f"  • Usefulness: {job.evaluation.usefulness:.0%}\n"
                f"  • Hallucination risk: {job.evaluation.hallucination_rate:.0%}"
            )

        summary = (
            f"🟩🟩🟩🟩 Done!\n\n"
            f"📚 {job.sources_count} sources · {job.evidence_count} evidence pieces · {job.themes_count} themes"
            f"{scores}"
        )
        if _msg_id[0]:
            _edit_telegram_message(chat_id, _msg_id[0], summary)

        report_html, mermaid_diagrams = _markdown_to_telegram_html(job.report)
        header = "<b>─── Report ───</b>\n\n"
        _send_telegram_chunked(chat_id, header + report_html, parse_mode="HTML")

        # Send each Mermaid diagram as a rendered image
        for i, diagram_code in enumerate(mermaid_diagrams, 1):
            photo_url = _mermaid_to_photo_url(diagram_code)
            caption = f"📊 Diagram {i}/{len(mermaid_diagrams)}" if len(mermaid_diagrams) > 1 else "📊 Diagram"
            _send_telegram_photo(chat_id, photo_url, caption=caption)

        # Send PDF as a downloadable file
        try:
            import markdown as md_lib
            import weasyprint

            html_body = md_lib.markdown(job.report, extensions=["tables", "fenced_code"])
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
            <style>body{{font-family:Georgia,serif;max-width:800px;margin:40px auto;font-size:11pt;line-height:1.6}}
            h1,h2,h3{{color:#00467f}}table{{border-collapse:collapse;width:100%}}
            th,td{{border:1px solid #ccc;padding:6px}}img{{max-width:100%}}</style>
            </head><body><h1>{job.question}</h1><hr>{html_body}</body></html>"""
            pdf_bytes = weasyprint.HTML(string=html).write_pdf()
            slug = re.sub(r"[^a-zA-Z0-9 _-]", "", question[:40]).strip().replace(" ", "_")
            _send_telegram_document(chat_id, f"{slug}_report.pdf", pdf_bytes, caption="📄 Full report as PDF")
        except Exception as exc:
            logger.warning("Could not generate PDF for Telegram: %s", exc)

    return on_complete


# ── Language preference store ────────────────────────────────────────────────
# Keyed by Telegram chat_id (int).  Survives for the lifetime of the process.
_user_language: dict[int | str, str] = {}

_LANG_OPTIONS = {
    "lang:en": "English",
    "lang:fr": "French",
}


def _send_telegram_inline_keyboard(
    chat_id: int | str,
    text: str,
    rows: list[list[dict]],
) -> int | None:
    """Send a message with an inline keyboard and return the message_id."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return None
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": rows},
    }
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        data = r.json()
        if data.get("ok"):
            return data["result"]["message_id"]
    except Exception as exc:
        logger.warning("_send_telegram_inline_keyboard failed: %s", exc)
    return None


def _answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a callback query to dismiss the spinner on the button."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("_answer_callback_query failed: %s", exc)


# ── Telegram webhook endpoint ────────────────────────────────────────────────

@router.post("/telegram")
async def telegram_inbound(request: Request):
    """Receive inbound Telegram messages (text or voice) and start research jobs."""
    body = await request.json()

    # ── Handle inline-keyboard callbacks (language selection) ─────────────────
    if "callback_query" in body:
        cq = body["callback_query"]
        cq_id = cq["id"]
        cq_data = cq.get("data", "")
        cq_chat_id = cq["message"]["chat"]["id"]

        if cq_data in _LANG_OPTIONS:
            lang = _LANG_OPTIONS[cq_data]
            _user_language[cq_chat_id] = lang
            _answer_callback_query(cq_id, f"Language set to {lang}")
            flag = "🇬🇧" if cq_data == "lang:en" else "🇫🇷"
            _send_telegram_message(
                cq_chat_id,
                f"{flag} Language set to *{lang}*\n\nNow send me your research question!",
            )
        else:
            _answer_callback_query(cq_id)

        return {"status": "callback_handled"}

    # ── Resolve question from text or voice ───────────────────────────────────
    text: str | None = None
    voice_note = False

    text_result = _extract_telegram_message(body)
    if text_result is not None:
        _, text = text_result
        chat_id = text_result[0]
    else:
        voice_result = _extract_telegram_voice(body)
        if voice_result is not None:
            chat_id, file_id = voice_result
            voice_note = True
            _send_telegram_chat_action(chat_id, "typing")
            _send_telegram_message(chat_id, "🎙️ Voice note received — transcribing…")

            audio_bytes = _download_telegram_voice(file_id)
            if audio_bytes is None:
                _send_telegram_message(chat_id, "❌ Could not download your voice note. Please try again.")
                return {"status": "error", "detail": "voice download failed"}

            text = _transcribe_voice(audio_bytes)
            if not text:
                _send_telegram_message(chat_id, "❌ Could not transcribe your voice note. Please try again or type your question.")
                return {"status": "error", "detail": "transcription failed"}

            _send_telegram_message(chat_id, f"✅ Transcribed: _{text}_")
        else:
            return {"status": "ignored"}

    # ── Handle commands ───────────────────────────────────────────────────────
    if text.startswith("/start"):
        _send_telegram_inline_keyboard(
            chat_id,
            "👋 Welcome to ML-ESS Research Assistant!\n\n"
            "I produce structured, evidence-backed research reports with quality scores.\n\n"
            "Please choose your preferred language:",
            rows=[
                [
                    {"text": "🇬🇧 English", "callback_data": "lang:en"},
                    {"text": "🇫🇷 Français", "callback_data": "lang:fr"},
                ]
            ],
        )
        return {"status": "start"}

    if text.startswith("/help"):
        _send_telegram_message(
            chat_id,
            "*ML-ESS Research Assistant*\n\n"
            "Send any research question as plain text or a 🎙️ voice note.\n\n"
            "The pipeline will:\n"
            "  🔍 Search the web for relevant sources\n"
            "  🧠 Synthesise evidence into themes\n"
            "  📝 Write a structured cited report\n"
            "  ✅ Evaluate coverage & faithfulness\n\n"
            "You'll receive live progress updates, the full report, and a PDF download.",
        )
        return {"status": "help"}

    if text.startswith("/"):
        _send_telegram_message(chat_id, "Unknown command. Send /help for usage.")
        return {"status": "ignored"}

    logger.info("Telegram %s from %s: %s", "voice" if voice_note else "text", chat_id, text[:80])

    # Show typing indicator and queue the job
    _send_telegram_chat_action(chat_id, "typing")

    status_msg_id = _send_telegram_message(
        chat_id,
        f"🔍 Research started!\n\nQuestion: {text[:200]}\n\n⬜⬜⬜⬜ Queued…",
    )

    job = create_job(
        text,
        on_progress=_make_telegram_progress_callback(chat_id, status_msg_id),
        on_complete=_make_telegram_complete_callback(chat_id, status_msg_id, text),
        language=_user_language.get(chat_id, "English"),
    )

    return {"status": "accepted", "job_id": job.job_id}


# ── Generic webhook endpoint ────────────────────────────────────────────────

@router.post("/inbound")
async def generic_inbound(event: WebhookEvent):
    """Generic webhook endpoint for any integration (Slack, custom frontend, etc.)."""
    if not event.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty.")

    job = create_job(event.message.strip())
    logger.info("Generic webhook job created: %s from %s", job.job_id, event.source)

    return {"status": "accepted", "job_id": job.job_id, "question": job.question}
