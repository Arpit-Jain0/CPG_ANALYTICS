"""
src/api/llm.py

LLM integration (Ollama) for /insights and /ask endpoints.

Ollama exposes an OpenAI-compatible API at $OLLAMA_BASE_URL (default
http://localhost:11434/v1). No API key is required — any string works.

Fallback behaviour when Ollama is unreachable:
  /insights → deterministic templated summary built from the aggregated data
  /ask      → "LLM unavailable" message with the bounded context rendered as text
"""

from __future__ import annotations

import logging

import httpx

from src.common.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0  # seconds — inference can be slow on CPU
_MAX_TOKENS = 768


# ── Internal LLM caller ───────────────────────────────────────────────────────


async def _call_llm(messages: list[dict]) -> str | None:
    """
    POST to Ollama's /chat/completions endpoint.
    Returns the response text, or None on any failure (connection error,
    timeout, HTTP error, model not yet loaded).
    """
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "max_tokens": _MAX_TOKENS,
        "temperature": 0.3,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer ollama",  # Ollama ignores this; kept for API-compat
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    except httpx.ConnectError:
        logger.warning(
            "Ollama not reachable at %s — using deterministic fallback", settings.ollama_base_url
        )
    except httpx.ReadTimeout:
        logger.warning("Ollama timed out after %.0fs — using deterministic fallback", _TIMEOUT)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Ollama HTTP %s: %s — using deterministic fallback",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.warning("Ollama call failed (%s) — using deterministic fallback", exc)

    return None


# ── Deterministic fallbacks ───────────────────────────────────────────────────


def _insights_summary(agg: dict) -> str:
    total = agg["total_revenue"]
    lines = [
        f"Total revenue: ${total:,.2f}",
        "",
        "By Category:",
        *[
            f"  {r['category']}: ${r['revenue']:,.2f}  ({r['revenue'] / total:.1%})"
            for r in agg["by_category"]
        ],
        "",
        "By Region:",
        *[
            f"  {r['region']}: ${r['revenue']:,.2f}  ({r['revenue'] / total:.1%})"
            for r in agg["by_region"]
        ],
    ]
    if agg["by_category"]:
        top = agg["by_category"][0]
        lines.append(
            f"\nLeading category '{top['category']}' accounts for "
            f"{top['revenue'] / total:.1%} of total revenue."
        )
    return "\n".join(lines)


# ── /insights ─────────────────────────────────────────────────────────────────

_INSIGHTS_SYSTEM = (
    "You are a CPG analytics assistant. "
    "Summarize the provided revenue figures in 3–5 concise bullet points. "
    "Use ONLY the numbers given — do not invent, estimate, or add external information. "
    "Be direct and factual."
)


async def generate_insights(agg: dict) -> tuple[str, bool]:
    """
    Returns (summary_text, llm_used).
    Tries Ollama first; falls back to _insights_summary on any failure.
    """
    total = agg["total_revenue"]
    figures = "\n".join(
        [
            f"Total revenue: ${total:,.2f}",
            "Revenue by category:",
            *[
                f"  {r['category']}: ${r['revenue']:,.2f} ({r['revenue'] / total:.1%})"
                for r in agg["by_category"]
            ],
            "Revenue by region:",
            *[
                f"  {r['region']}: ${r['revenue']:,.2f} ({r['revenue'] / total:.1%})"
                for r in agg["by_region"]
            ],
        ]
    )

    messages = [
        {"role": "system", "content": _INSIGHTS_SYSTEM},
        {"role": "user", "content": f"Summarize these figures:\n\n{figures}"},
    ]

    result = await _call_llm(messages)
    if result:
        return result, True

    return _insights_summary(agg), False


# ── /ask ──────────────────────────────────────────────────────────────────────

_ASK_SYSTEM = (
    "You are a CPG analytics assistant. "
    "Answer the user's question using ONLY the data provided in the context below. "
    "Do not use external knowledge or invent figures. "
    "If the answer cannot be determined from the context, say so explicitly."
)


async def answer_question(context: str, question: str) -> tuple[str, bool]:
    """
    Returns (answer_text, llm_used).
    Tries Ollama first; on failure returns a 'LLM unavailable' response
    with the bounded context rendered as plain text so the user still has
    the underlying data.
    """
    messages = [
        {"role": "system", "content": _ASK_SYSTEM},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]

    result = await _call_llm(messages)
    if result:
        return result, True

    fallback = (
        "LLM unavailable — here are the relevant figures from your data:\n\n"
        f"{context}\n\n"
        f"Question asked: {question}"
    )
    return fallback, False
