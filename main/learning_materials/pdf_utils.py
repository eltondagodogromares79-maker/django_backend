from io import BytesIO
from typing import Iterable
import os
import re
from datetime import datetime

from django.conf import settings


def _wrap_text(text: str, max_chars: int = 95) -> Iterable[str]:
    words = text.split()
    line = []
    length = 0
    for word in words:
        if length + len(word) + (1 if line else 0) > max_chars:
            yield " ".join(line)
            line = [word]
            length = len(word)
        else:
            line.append(word)
            length += len(word) + (1 if line else 0)
    if line:
        yield " ".join(line)


def _find_image_urls(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(r"https?://\\S+?\\.(?:png|jpg|jpeg|webp)", re.IGNORECASE)
    return pattern.findall(text)


def _extract_jsonish_fields(text: str) -> dict:
    if not text:
        return {}
    result: dict[str, str] = {}
    for key in ["title", "description", "content"]:
        match = re.search(rf"\"{key}\"\\s*:\\s*\"", text)
        if not match:
            continue
        idx = match.end()
        chars: list[str] = []
        escaped = False
        while idx < len(text):
            ch = text[idx]
            if escaped:
                chars.append(ch)
                escaped = False
            else:
                if ch == "\\":
                    escaped = True
                elif ch == "\"":
                    break
                else:
                    chars.append(ch)
            idx += 1
        value = "".join(chars).replace("\\n", "\n").replace("\\t", "\t").strip()
        if value:
            result[key] = value
    return result


def clean_lesson_body(body: str) -> str:
    if not body:
        return ""
    text = body.strip()
    if "\"content\"" in text:
        parsed = _extract_jsonish_fields(text)
        if parsed:
            parts = [parsed.get("description", "").strip(), parsed.get("content", "").strip()]
            combined = "\n\n".join([p for p in parts if p]).strip()
            if combined:
                return combined
        # Fallback extraction if JSON is malformed
        desc_match = re.search(r"\"description\"\\s*:\\s*\"", text)
        content_match = re.search(r"\"content\"\\s*:\\s*\"", text)
        description = ""
        content = ""
        if desc_match:
            desc_start = desc_match.end()
            desc_end = text.find("\"content\"", desc_start)
            if desc_end == -1:
                desc_end = len(text)
            raw_desc = text[desc_start:desc_end]
            raw_desc = raw_desc.strip().rstrip(",").strip().strip('"')
            description = raw_desc
        if content_match:
            content_start = content_match.end()
            raw_content = text[content_start:].strip()
            raw_content = re.sub(r"\"\\s*}\\s*$", "", raw_content)
            raw_content = raw_content.strip().strip('"')
            content = raw_content
        combined = "\n\n".join([p for p in [description, content] if p.strip()]).strip()
        combined = combined.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"")
        if combined:
            return combined
        # Aggressive cleanup: strip JSON keys and keep text
        cleaned = text
        cleaned = re.sub(r"^\\s*\\{\\s*\"title\"\\s*:\\s*\".*?\"\\s*,", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\"resource_url\"\\s*:\\s*\".*?\"\\s*,?", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\"description\"\\s*:\\s*\"", "", cleaned)
        cleaned = re.sub(r"\"\\s*,\\s*\"content\"\\s*:\\s*\"", "\n\n", cleaned)
        cleaned = re.sub(r"\"\\s*}\\s*$", "", cleaned)
        cleaned = cleaned.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"")
        cleaned = cleaned.strip().strip('"').strip()
        if cleaned:
            return cleaned
    return body


def _get_logo_path() -> str | None:
    logo_path = getattr(settings, "PDF_LOGO_PATH", "") or ""
    if not logo_path:
        return None
    if os.path.isabs(logo_path):
        return logo_path if os.path.exists(logo_path) else None
    candidate = os.path.join(settings.BASE_DIR, logo_path)
    return candidate if os.path.exists(candidate) else None


def generate_pdf_filename(title: str, subject_code: str | None) -> str:
    template = getattr(settings, "PDF_FILENAME_TEMPLATE", "") or "{subject}-{title}-{date}.pdf"
    subject = (subject_code or "learning-material").strip()
    date = datetime.now().strftime("%Y%m%d")
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-") or "learning-material"
    safe_subject = re.sub(r"[^a-zA-Z0-9_-]+", "-", subject).strip("-") or "learning-material"
    filename = template.format(subject=safe_subject, title=safe_title, date=date)
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    return filename


def generate_pdf_bytes(
    title: str,
    body: str,
    *,
    subject_code: str | None = None,
    resource_url: str | None = None,
) -> bytes:
    try:
        from reportlab.lib.pagesizes import LETTER  # type: ignore
        from reportlab.lib.utils import ImageReader  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab") from exc

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    logo_path = _get_logo_path()
    header_text = getattr(settings, "PDF_HEADER_TEXT", "") or ""
    footer_text = getattr(settings, "PDF_FOOTER_TEXT", "") or ""

    y = height - 72
    if logo_path:
        try:
            c.drawImage(logo_path, 72, y - 20, width=48, height=48, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72 + (60 if logo_path else 0), y + 8, title[:120])
    if header_text:
        c.setFont("Helvetica", 9)
        c.drawRightString(width - 72, y + 12, header_text)

    y -= 28
    c.setFont("Helvetica", 11)
    cleaned_body = clean_lesson_body(body or "")
    for paragraph in (cleaned_body or "").splitlines():
        if not paragraph.strip():
            y -= 12
            continue
        line_text = paragraph.strip()
        is_heading = bool(re.match(r"^(\\d+[\\).]|[A-Za-z].*:)$", line_text))
        is_bullet = line_text.startswith(("-", "*", "•"))
        if is_heading:
            c.setFont("Helvetica-Bold", 12)
        else:
            c.setFont("Helvetica", 11)
        if is_bullet:
            line_text = line_text.lstrip("-*•").strip()
            line_text = f"• {line_text}"
        for line in _wrap_text(line_text, max_chars=95):
            if y < 72:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 72
            c.drawString(72, y, line)
            y -= 14
        if is_heading:
            c.setFont("Helvetica", 11)
        y -= 8

    # Append images on new pages if any URLs are present
    image_urls = _find_image_urls(body)
    if resource_url and resource_url.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        image_urls.insert(0, resource_url)

    if image_urls:
        try:
            import requests  # type: ignore
        except Exception:
            image_urls = []

    if image_urls:
        c.showPage()
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, "Learning Material Images")
        y = height - 110
        for url in image_urls:
            try:
                response = requests.get(url, timeout=15)
                response.raise_for_status()
                img = ImageReader(BytesIO(response.content))
                img_width, img_height = img.getSize()
                max_width = width - 144
                max_height = height - 180
                scale = min(max_width / img_width, max_height / img_height, 1.0)
                draw_w = img_width * scale
                draw_h = img_height * scale
                if y - draw_h < 72:
                    c.showPage()
                    y = height - 72
                c.drawImage(img, 72, y - draw_h, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
                y -= draw_h + 24
            except Exception:
                continue

    c.showPage()
    if footer_text:
        c.setFont("Helvetica", 9)
        c.drawString(72, 36, footer_text)
    c.save()
    buffer.seek(0)
    return buffer.read()
