"""
Thin wrapper around the LLM API (Gemini or Grok).

Why this file exists:
This is the ONLY file in the project that talks to an LLM API directly.
Every other module that needs the LLM (website_analyzer.py,
email_generator.py, contact_finder.py) calls the function here instead
of importing a provider's SDK themselves. Which provider is actually
used is decided in one place - settings.LLM_PROVIDER - so switching
providers, or adding a third one later, never touches those other
files.
"""

import time

from google import genai
from google.genai import types
from openai import OpenAI

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# A single place to change which model each provider uses.
#
# Google's and xAI's model lineups both move fast - models get
# deprecated with fairly short notice. If you hit a 404 error naming a
# model, that's what's happening: update the matching constant below.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GROK_MODEL = "grok-4-6"

# How many times to retry a call that fails because the API is busy
# (overloaded/rate-limited), and how long to wait before each retry.
# Waits grow each attempt (2s, 4s, 8s) - "exponential backoff" - since
# retrying instantly into a busy server rarely helps.
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2


def _call_gemini_once(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """Make one (non-retried) request to Gemini and return the reply text."""
    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=60_000),
    )
    response = client.models.generate_content(
        model=DEFAULT_GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _call_grok_once(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """
    Make one (non-retried) request to xAI's Grok API.

    Grok's API is OpenAI-compatible, so we reuse the standard "openai"
    Python package and just point it at xAI's server (base_url) with
    your xAI key instead of an OpenAI key.
    """
    client = OpenAI(api_key=settings.XAI_API_KEY, base_url="https://api.x.ai/v1")
    response = client.chat.completions.create(
        model=DEFAULT_GROK_MODEL,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """
    Send one request to whichever LLM provider is configured
    (settings.LLM_PROVIDER: "gemini" or "grok") and return the text of
    its reply.

    Every prompt in this project asks the model to reply with ONLY a
    JSON object, so both provider functions above turn on that
    provider's JSON output mode.

    If the API reports it's busy/overloaded, this retries a few times
    with a growing delay before giving up - a normal, expected
    condition on free-tier keys, not a bug.

    Raises RuntimeError if the relevant API key isn't configured, or
    ValueError if LLM_PROVIDER is set to something unrecognized -
    neither of these is retried, since retrying won't fix a
    configuration problem. Raises the underlying provider error (after
    logging it and exhausting retries) for any other API failure.
    """
    provider_name = (settings.LLM_PROVIDER or "gemini").lower()

    if provider_name == "gemini":
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
        provider_function = _call_gemini_once
    elif provider_name == "grok":
        if not settings.XAI_API_KEY:
            raise RuntimeError("XAI_API_KEY is not set. Add it to your .env file.")
        provider_function = _call_grok_once
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider_name}'. Use 'gemini' or 'grok'.")

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return provider_function(system_prompt, user_prompt, max_tokens)
        except Exception as error:
            last_error = error
            is_last_attempt = attempt == MAX_RETRIES

            if is_last_attempt:
                logger.error(f"{provider_name} API call failed after {MAX_RETRIES} attempts: {error}")
                raise

            wait_seconds = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"{provider_name} API call failed (attempt {attempt}/{MAX_RETRIES}): {error}. "
                f"Retrying in {wait_seconds}s..."
            )
            time.sleep(wait_seconds)

    raise last_error