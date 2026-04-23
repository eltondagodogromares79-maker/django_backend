import json
import re
import time
from typing import Tuple

from django.conf import settings


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class RateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


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
            return {}
    return {}


def _extract_jsonish_fields(text: str) -> dict:
    if not text:
        return {}
    result: dict[str, str] = {}
    for key in ["title", "description", "questions"]:
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


def _normalize_assignment_body(text: str) -> str:
    if not text:
        return ""
    raw = text.strip()
    parsed = _extract_json(raw)
    if not parsed:
        parsed = _extract_jsonish_fields(raw)
    if parsed:
        description = parsed.get("description") or ""
        questions = parsed.get("questions") or ""
        parts = [description.strip(), questions.strip()]
        combined = "\n\n".join([p for p in parts if p]).strip()
        if combined:
            return combined
    return raw.replace("\\n", "\n").replace("\\t", "\t").replace("\\\"", "\"").strip()


def _safe_score(value, total_points: float) -> float:
    try:
        score = float(value)
    except Exception:
        score = 0.0
    if score < 0:
        score = 0.0
    if total_points is not None and score > total_points:
        score = float(total_points)
    return score


def grade_assignment_with_gemini(
    *,
    assignment_title: str,
    assignment_description: str | None,
    total_points: float,
    student_answer: str,
) -> Tuple[float, str]:
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("requests is not installed. Run: pip install requests") from exc

    model = getattr(settings, "GEMINI_MODEL", "") or DEFAULT_GEMINI_MODEL
    api_base = getattr(settings, "GEMINI_API_BASE", "") or DEFAULT_GEMINI_API_BASE
    endpoint = f"{api_base}/models/{model}:generateContent"
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    prompt = (
        "You are an assistant grading a student assignment.\n"
        "Return ONLY a JSON object with keys: score (number) and feedback (string).\n"
        "Do not include markdown, code fences, or extra text.\n"
        f"Total points: {total_points}\n"
        f"Assignment title: {assignment_title}\n"
        f"Assignment description: {assignment_description or 'N/A'}\n"
        "Student answer:\n"
        f"{student_answer}\n"
        "Scoring must be between 0 and total points.\n"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 512,
            "response_mime_type": "application/json",
        },
    }

    response = requests.post(
        endpoint,
        params={"key": api_key},
        json=payload,
        timeout=20,
    )
    if response.status_code == 429:
        raise RateLimitError("Rate limited — try again in 60s.", retry_after=60)
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No AI grading response returned.")

    text_parts = candidates[0].get("content", {}).get("parts", [])
    if not text_parts:
        raise RuntimeError("AI response was empty.")

    raw_text = text_parts[0].get("text", "")
    parsed = _extract_json(raw_text)
    score = _safe_score(parsed.get("score"), total_points)
    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        feedback = raw_text.strip()

    return score, feedback


def generate_assignment_with_gemini(
    *,
    prompt: str,
    subject_name: str,
    subject_code: str,
    total_points: float,
) -> Tuple[str, str, float]:
    try:
        import requests  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("requests is not installed. Run: pip install requests") from exc

    model = getattr(settings, "GEMINI_MODEL", "") or DEFAULT_GEMINI_MODEL
    api_base = getattr(settings, "GEMINI_API_BASE", "") or DEFAULT_GEMINI_API_BASE
    endpoint = f"{api_base}/models/{model}:generateContent"
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    prompt_text = (
        "You are an assistant that creates teacher assignments.\n"
        "Return ONLY a JSON object with keys:\n"
        "title (string), description (string), questions (string), total_points (number).\n"
        "Do not include markdown or extra text.\n"
        f"Subject: {subject_name} ({subject_code})\n"
        f"Requested total points: {total_points}\n"
        f"Teacher request: {prompt}\n"
        "Include clear instructions, questions, and submission expectations.\n"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2500,
            "response_mime_type": "application/json",
        },
    }

    backoff_seconds = [2, 4, 8]
    for attempt in range(1 + len(backoff_seconds)):
        response = requests.post(
            endpoint,
            params={"key": api_key},
            json=payload,
            timeout=25,
        )
        if response.status_code == 429:
            if attempt < len(backoff_seconds):
                time.sleep(backoff_seconds[attempt])
                continue
            raise RateLimitError("Rate limited — try again in 60s.", retry_after=60)
        if response.status_code >= 500 and attempt < len(backoff_seconds):
            time.sleep(backoff_seconds[attempt])
            continue
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("No AI assignment response returned.")
        text_parts = candidates[0].get("content", {}).get("parts", [])
        if not text_parts:
            raise RuntimeError("AI response was empty.")
        raw_text = "\n".join(part.get("text", "") for part in text_parts if isinstance(part, dict)).strip()
        parsed = _extract_json(raw_text)
        if not parsed:
            parsed = _extract_jsonish_fields(raw_text)
        title = parsed.get("title") if isinstance(parsed, dict) else None
        description = parsed.get("description") if isinstance(parsed, dict) else None
        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        suggested_points = parsed.get("total_points") if isinstance(parsed, dict) else None
        body = _normalize_assignment_body(raw_text)
        if description or questions:
            body = _normalize_assignment_body(
                json.dumps({
                    "description": description or "",
                    "questions": questions or "",
                })
            )
        if not title:
            title = f"{subject_name} Assignment"
        final_points = _safe_score(suggested_points, total_points) if suggested_points is not None else total_points
        return title, body, final_points

    raise RuntimeError("AI assignment generation failed.")
