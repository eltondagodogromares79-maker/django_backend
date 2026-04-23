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


def _call_gemini(prompt_text: str, max_tokens: int = 2500) -> dict:
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

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": max_tokens,
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
            raise RuntimeError("No AI response returned.")
        text_parts = candidates[0].get("content", {}).get("parts", [])
        if not text_parts:
            raise RuntimeError("AI response was empty.")
        raw_text = "\n".join(part.get("text", "") for part in text_parts if isinstance(part, dict)).strip()
        parsed = _extract_json(raw_text)
        if parsed:
            return parsed
        return {"raw": raw_text}

    raise RuntimeError("AI generation failed.")


def generate_quiz_with_gemini(
    *,
    prompt: str,
    subject_name: str,
    subject_code: str,
) -> dict:
    prompt_text = (
        "You are an assistant that creates a quiz for teachers.\n"
        "Return ONLY JSON with keys: title, description, time_limit_minutes, attempt_limit, questions.\n"
        "questions must be an array of objects with keys:\n"
        "question_text, question_type (multiple_choice, true_false, essay, identification), points,\n"
        "choices (array of {text, is_correct}) for multiple_choice or true_false.\n"
        "Do not include markdown or extra text.\n"
        f"Subject: {subject_name} ({subject_code})\n"
        f"Teacher request: {prompt}\n"
        "Keep the quiz to 5-10 questions unless specified otherwise.\n"
    )
    return _call_gemini(prompt_text, max_tokens=3000)


def grade_quiz_answer_with_gemini(
    *,
    question_text: str,
    student_answer: str,
    points: float,
) -> Tuple[float, str]:
    prompt_text = (
        "You are grading a student quiz answer.\n"
        "Return ONLY JSON with keys: score (number) and feedback (string).\n"
        f"Total points: {points}\n"
        f"Question: {question_text}\n"
        f"Student answer:\n{student_answer}\n"
        "Score must be between 0 and total points.\n"
    )
    parsed = _call_gemini(prompt_text, max_tokens=512)
    score = _safe_score(parsed.get("score"), points)
    feedback = parsed.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        feedback = "AI graded response."
    return score, feedback
