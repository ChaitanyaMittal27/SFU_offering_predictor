"""
src/gemini.py  —  Gemini Interface Layer

Owns all Gemini API interaction: client setup, prompts, and two public functions.

Public API:
    get_client()                          → Gemini client or None
    extract_params(client, ctx, msg)      → dict (params or error)
    format_response(client, result, msg)  → str (plain English)

app.py imports these — it never touches the google.genai SDK directly.
"""

import os
import json

_MODEL = "gemini-3-flash-preview"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
def get_client():
    """
    Return a configured Gemini client, or None if no API key is found.
    Tries st.secrets first (Streamlit Cloud), then .env file.
    """
    key = _get_api_key()
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except Exception:
        return None


def _get_api_key() -> str:
    try:
        import streamlit as st
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv("GEMINI_API_KEY", "")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------
def _extraction_prompt(ctx: dict) -> str:
    """
    System prompt for parameter extraction.
    Kept short to stay within free-tier token limits.
    """
    sample = ctx["course_pairs"][:25]
    yr     = ctx["year_range"]["min"]
    depts  = ", ".join(ctx["depts"][:30])

    hints  = "\n".join(
        f'{c["dept"]} {c["course_num"]} — {c["title"]}'
        for c in sample
    )

    return f"""You extract SFU course prediction parameters from casual user messages.

DEPARTMENTS: {depts} (and more)
SEMESTERS: spring, summer, fall
DEFAULT YEAR if not mentioned: {yr}
DEFAULT SEMESTER if not mentioned: fall

COURSE HINTS — use to resolve course names to dept + code:
{hints}

RULES:
- Be flexible: "cmpt 225", "CMPT225", "data structures" all → CMPT 225
- "autumn" → fall. Missing year → {yr}. Missing semester → fall.
- Output ONLY a JSON object, no explanation, no markdown.

Success: {{"dept":"CMPT","course_num":"225","semester":"fall","year":{yr}}}
Unknown course: {{"error":"brief reason"}}"""


def _response_prompt(result: dict, user_msg: str) -> str:
    return (
        f'User asked: "{user_msg}"\n'
        f"Result: {json.dumps(result)}\n\n"
        "Write 2-3 friendly sentences explaining the prediction. "
        "No bullet points. No markdown. Pick the most meaningful numbers."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_params(client, ctx: dict, user_msg: str) -> dict:
    """
    First Gemini call: parse user message → structured prediction parameters.

    Returns one of:
        {"dept": "CMPT", "course_num": "225", "semester": "fall", "year": 2027}
        {"error": "human-readable explanation"}
    """
    prompt = _extraction_prompt(ctx) + f"\n\nUser: {user_msg}"
    try:
        r    = client.models.generate_content(model=_MODEL, contents=prompt)
        text = r.text.strip().replace("```json", "").replace("```", "").strip()
        s    = text.find("{")
        e    = text.rfind("}") + 1
        if s == -1 or e == 0:
            return {"error": "I couldn't identify the course. Try: 'CMPT 225 fall 2027'"}
        return json.loads(text[s:e])
    except json.JSONDecodeError:
        return {"error": "Couldn't parse that. Try rephrasing, e.g. 'Will CMPT 225 run in Fall 2027?'"}
    except Exception as ex:
        s = str(ex).lower()
        if "429" in str(ex) or "quota" in s or "exhausted" in s:
            return {"error": "⏳ Rate limit reached. Wait a minute and try again."}
        return {"error": "Something went wrong with the AI. Try again."}


def format_response(client, result: dict, user_msg: str) -> str:
    """
    Second Gemini call: turn a prediction result dict → plain English reply.
    Falls back to a hardcoded template if the API call fails.
    """
    try:
        r = client.models.generate_content(
            model=_MODEL,
            contents=_response_prompt(result, user_msg),
        )
        return r.text.strip()
    except Exception:
        return _fallback_response(result)


def _fallback_response(result: dict) -> str:
    """Plain-text fallback when Gemini is unavailable."""
    if result["status"] != "ok":
        return result.get("error", "Something went wrong.")
    p = result["offered_prob"] * 100
    return (
        f"{result['dept']} {result['course_num']} has a {p:.0f}% chance of running "
        f"in {result['semester'].capitalize()} {result['year']} — "
        f"expecting {result['enrollment']} students out of {result['capacity']} seats."
    )