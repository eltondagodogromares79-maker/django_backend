import json
import re
import threading
import time
import logging
from typing import Tuple

from django.conf import settings


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_AI_LOCK = threading.Lock()
_LOGGER = logging.getLogger("learning_materials.ai")


class RateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


def _extract_jsonish_fields(text: str) -> dict:
    if not text:
        return {}
    result: dict[str, str] = {}
    for key in ["title", "description", "content", "resource_url"]:
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


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            jsonish = _extract_jsonish_fields(match.group(0))
            if jsonish:
                return jsonish
            return {}
    jsonish = _extract_jsonish_fields(text)
    if jsonish:
        return jsonish
    return {}


def _normalize_body(body: str) -> str:
    if not body:
        return ""
    normalized = body.replace("\\n", "\n")
    if normalized.strip().startswith("{") and "title" in normalized:
        parsed = _extract_json(normalized)
        if parsed:
            desc = parsed.get("description") or ""
            content = parsed.get("content") or ""
            parts = [desc.strip(), content.strip()]
            normalized = "\n\n".join([p for p in parts if p]).strip()
            if not normalized:
                return body.strip()
        else:
            return body.strip()
    # Remove basic markdown bold markers
    normalized = re.sub(r"\*\*(.+?)\*\*", r"\1", normalized)
    return normalized.strip()


def _sanitize_jsonish_body(body: str) -> str:
    if not body:
        return ""
    text = body.strip()
    if "\"content\"" not in text and "\"description\"" not in text:
        return body
    # Best-effort extraction without strict JSON parsing
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
        raw_desc = raw_desc.strip()
        if raw_desc.endswith(","):
            raw_desc = raw_desc[:-1]
        description = raw_desc.strip().strip('"')
    if content_match:
        content_start = content_match.end()
        raw_content = text[content_start:].strip()
        # Trim trailing JSON-ish endings
        raw_content = re.sub(r"\"\\s*}\\s*$", "", raw_content)
        raw_content = raw_content.strip().strip('"')
        content = raw_content
    combined = "\n\n".join([part for part in [description, content] if part.strip()]).strip()
    combined = combined.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"")
    if combined:
        return combined
    # Aggressive cleanup as last resort
    cleaned = text
    cleaned = re.sub(r"^\\s*\\{\\s*\"title\"\\s*:\\s*\".*?\"\\s*,", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\"resource_url\"\\s*:\\s*\".*?\"\\s*,?", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\"description\"\\s*:\\s*\"", "", cleaned)
    cleaned = re.sub(r"\"\\s*,\\s*\"content\"\\s*:\\s*\"", "\n\n", cleaned)
    cleaned = re.sub(r"\"\\s*}\\s*$", "", cleaned)
    cleaned = cleaned.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"")
    cleaned = cleaned.strip().strip('"').strip()
    return cleaned if cleaned else body


def _detect_lesson_plan_type(prompt: str) -> str | None:
    if not prompt:
        return None
    lowered = prompt.lower()
    if "lesson plan" not in lowered:
        return None
    match = re.search(r"lesson\\s*plan\\s*type\\s*[:=\\-]\\s*(dll|dlp)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"\\b(dll|dlp)\\b", prompt, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _build_deped_prompt(
    *,
    prompt: str,
    subject_name: str,
    subject_code: str,
    lesson_type: str,
    plan_type: str,
) -> str:
    return (
        "You are an expert teacher from the Department of Education (DepEd) in the Philippines.\n"
        "Generate a lesson plan based on DepEd Order No. 42, s. 2016.\n"
        "STRICT RULES:\n"
        "- Follow the correct structure EXACTLY depending on the selected type.\n"
        "- Do NOT skip any section.\n"
        "- Do NOT add extra sections or explanations.\n"
        "- Use formal and clear teaching language.\n"
        "- Keep responses structured and ready for Word/PDF export.\n"
        "- If a field has no data, write \"N/A\".\n"
        "Return ONLY a JSON object with keys:\n"
        "title (string), description (string), content (string), resource_url (string or null).\n"
        "Do not include markdown or extra text.\n"
        "Put the full lesson plan in content. Use an empty string for description.\n"
        f"Subject: {subject_name} ({subject_code})\n"
        f"Requested lesson type: {lesson_type}\n"
        f"Lesson Plan Type: {plan_type}\n"
        "INPUT (use these values exactly, fill missing with N/A):\n"
        f"{prompt}\n"
        "\n"
        "IF Lesson Plan Type = \"DLL\", FOLLOW THIS FORMAT:\n"
        "\n"
        "DAILY LESSON LOG (DLL)\n"
        "\n"
        "I. OBJECTIVES\n"
        "A. Content Standard:\n"
        "B. Performance Standard:\n"
        "C. Learning Competency:\n"
        "\n"
        "II. CONTENT:\n"
        "\n"
        "III. LEARNING RESOURCES\n"
        "A. References:\n"
        "B. Other Learning Resources:\n"
        "\n"
        "IV. PROCEDURES\n"
        "A. Reviewing previous lesson:\n"
        "B. Establishing a purpose:\n"
        "C. Presenting examples:\n"
        "D. Discussing new concepts #1:\n"
        "E. Discussing new concepts #2:\n"
        "F. Developing mastery:\n"
        "G. Application:\n"
        "H. Generalization:\n"
        "I. Evaluation:\n"
        "J. Additional activities:\n"
        "\n"
        "V. REMARKS:\n"
        "\n"
        "VI. REFLECTION\n"
        "A. No. of learners who earned 80%:\n"
        "B. No. of learners who need remediation:\n"
        "C. Did the lesson work well? Why?\n"
        "D. Difficulties encountered:\n"
        "E. Innovation or strategy:\n"
        "\n"
        "IF Lesson Plan Type = \"DLP\", FOLLOW THIS FORMAT:\n"
        "\n"
        "DETAILED LESSON PLAN (DLP)\n"
        "\n"
        "I. OBJECTIVES\n"
        "(Provide 3 specific objectives)\n"
        "\n"
        "II. SUBJECT MATTER\n"
        "Topic:\n"
        "Materials:\n"
        "References:\n"
        "\n"
        "III. PROCEDURE\n"
        "\n"
        "A. Preliminary Activities\n"
        "- Prayer\n"
        "- Greetings\n"
        "- Attendance\n"
        "- Review\n"
        "\n"
        "B. Motivation\n"
        "\n"
        "C. Presentation of the Lesson\n"
        "\n"
        "D. Discussion\n"
        "(Must include Teacher: and Students: interaction)\n"
        "\n"
        "E. Activity\n"
        "\n"
        "F. Generalization\n"
        "\n"
        "G. Application\n"
        "\n"
        "H. Evaluation\n"
        "\n"
        "I. Assignment\n"
        "\n"
        "IV. REMARKS\n"
        "\n"
        "V. REFLECTION\n"
    )


def _call_gemini(prompt_text: str, api_key: str, endpoint: str) -> dict:
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("requests is not installed. Run: pip install requests") from exc

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 6000,
            "response_mime_type": "application/json",
        },
    }
    backoff_seconds = [2, 4, 8]

    with _AI_LOCK:
        for attempt in range(1 + len(backoff_seconds)):
            response = requests.post(
                endpoint,
                params={"key": api_key},
                json=payload,
                timeout=25,
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60") or "60")
                if attempt < len(backoff_seconds):
                    time.sleep(backoff_seconds[attempt])
                    continue
                raise RateLimitError("Rate limited — try again in 60s.", retry_after=retry_after)

            if response.status_code >= 500 and attempt < len(backoff_seconds):
                time.sleep(backoff_seconds[attempt])
                continue

            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No AI response returned.")
            text_parts = candidates[0].get("content", {}).get("parts", [])
            if not text_parts:
                raise RuntimeError("AI response was empty.")

            raw_text = "\n".join(
                part.get("text", "") for part in text_parts if isinstance(part, dict)
            ).strip()
            if not raw_text:
                raise RuntimeError("AI response was empty.")
            parsed = _extract_json(raw_text)
            if not parsed and raw_text:
                return {"content": raw_text}
            return parsed

    raise RuntimeError("AI generation failed.")


def generate_lesson_with_gemini(
    *,
    prompt: str,
    subject_name: str,
    subject_code: str,
    lesson_type: str,
) -> Tuple[str, str, str | None]:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    model = getattr(settings, "GEMINI_MODEL", "") or DEFAULT_GEMINI_MODEL
    api_base = getattr(settings, "GEMINI_API_BASE", "") or DEFAULT_GEMINI_API_BASE
    endpoint = f"{api_base}/models/{model}:generateContent"

    plan_type = _detect_lesson_plan_type(prompt)
    if plan_type in ["DLL", "DLP"]:
        prompt_text = _build_deped_prompt(
            prompt=prompt,
            subject_name=subject_name,
            subject_code=subject_code,
            lesson_type=lesson_type,
            plan_type=plan_type,
        )
    else:
        prompt_text = (
            "You are an assistant that creates learning materials for teachers.\n"
            "Return ONLY a JSON object with keys:\n"
            "title (string), description (string), content (string), resource_url (string or null).\n"
            "Do not include markdown or extra text.\n"
            f"Subject: {subject_name} ({subject_code})\n"
            f"Requested material type: {lesson_type}\n"
            f"Teacher request: {prompt}\n"
            "If the request is short, expand it into a full learning material.\n"
            "For text/pdf materials, provide structured content with:\n"
            "1) Objectives, 2) Key concepts, 3) Lesson flow, 4) Activities, 5) Assessment.\n"
            "If the type is 'link' or 'video', include a helpful resource_url.\n"
        )

    parsed = _call_gemini(prompt_text, api_key, endpoint)

    title = parsed.get("title") or f"{subject_name} Learning Material"
    description = parsed.get("description") or ""
    content = parsed.get("content") or ""
    resource_url = parsed.get("resource_url")
    if resource_url and not isinstance(resource_url, str):
        resource_url = None

    body_parts = [description.strip(), content.strip()]
    body = "\n\n".join([part for part in body_parts if part]).strip()
    body = _normalize_body(body)
    body = _sanitize_jsonish_body(body)

    if plan_type not in ["DLL", "DLP"] and lesson_type in ['text', 'pdf'] and len(body) < 400:
        expansion_prompt = (
            "Expand the following draft into a complete learning material.\n"
            "Return ONLY JSON with keys: title, description, content, resource_url.\n"
            "The learning material should be at least 600 words and include:\n"
            "Objectives, Key concepts, Lesson flow, Activities, Assessment.\n"
            f"Subject: {subject_name} ({subject_code})\n"
            f"Original request: {prompt}\n"
            f"Draft content:\n{body}\n"
        )
        expanded = _call_gemini(expansion_prompt, api_key, endpoint)
        title = expanded.get("title") or title
        description = expanded.get("description") or description
        content = expanded.get("content") or content
        resource_url = expanded.get("resource_url") or resource_url
        body_parts = [description.strip(), content.strip()]
        body = "\n\n".join([part for part in body_parts if part]).strip()
        body = _normalize_body(body)
        body = _sanitize_jsonish_body(body)

    if plan_type not in ["DLL", "DLP"] and lesson_type in ['text', 'pdf']:
        needs_completion = (
            len(body) < 1200
            or "Assessment" not in body
            or "Objectives" not in body
            or "Lesson Flow" not in body
        )
        if needs_completion:
            completion_prompt = (
                "Complete and finalize the learning material below. Return ONLY JSON with keys:\n"
                "title, description, content, resource_url.\n"
                "Ensure the final learning material includes: Objectives, Key concepts, Lesson flow,\n"
                "Activities, Assessment, and a short exit quiz. If content already exists,\n"
                "extend it with the missing parts and keep the same topic.\n"
                f"Subject: {subject_name} ({subject_code})\n"
                f"Original request: {prompt}\n"
                f"Current draft:\n{body}\n"
            )
            completed = _call_gemini(completion_prompt, api_key, endpoint)
            title = completed.get("title") or title
            description = completed.get("description") or description
            content = completed.get("content") or content
            resource_url = completed.get("resource_url") or resource_url
            body_parts = [description.strip(), content.strip()]
            body = "\n\n".join([part for part in body_parts if part]).strip()
            body = _normalize_body(body)
            body = _sanitize_jsonish_body(body)

    if getattr(settings, "AI_LOG_OUTPUT", "false").lower() in ["1", "true", "yes"]:
        log_text = (
            "\n--- AI LEARNING MATERIAL OUTPUT ---\n"
            f"Title: {title}\n"
            f"Resource URL: {resource_url}\n"
            "Body:\n\n"
            f"{body}\n"
            "--- END AI LEARNING MATERIAL OUTPUT ---\n"
        )
        print(log_text)
        _LOGGER.warning(log_text)

    return title, body, resource_url
