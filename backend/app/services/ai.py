"""AI enrichment service for StashAI using LiteLLM."""

import json
import logging

logger = logging.getLogger(__name__)

# Curated model list by provider
PROVIDER_MODELS = {
    "anthropic": [
        {"id": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 (fast, cheap)"},
        {"id": "anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (balanced)"},
        {"id": "anthropic/claude-opus-4-6", "label": "Claude Opus 4.6 (most capable)"},
    ],
    "openai": [
        {"id": "openai/gpt-5-mini", "label": "GPT-5 Mini (fast, affordable)"},
        {"id": "openai/gpt-5.4", "label": "GPT-5.4 (frontier)"},
        {"id": "openai/o4-mini", "label": "o4-mini (reasoning)"},
    ],
    "google": [
        {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash (fast, cheap)"},
        {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro (capable)"},
        {"id": "gemini/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro (preview)"},
    ],
    "ollama": [
        {"id": "ollama/llama3.3", "label": "Llama 3.3 (local)"},
        {"id": "ollama/mistral", "label": "Mistral (local)"},
        {"id": "ollama/gemma2", "label": "Gemma 2 (local)"},
    ],
}

ENRICHMENT_PROMPT = """You are a link summarization assistant. Given a URL and its page content (title, description), produce a JSON response with:

1. "title": A concise, descriptive title (max 80 chars). If the original title is good, clean it up. If it's a repo or technical page, make it human-readable.
2. "summary": A 1-2 sentence summary of what this link is about and why someone would save it.
3. "tags": An array of 2-5 lowercase tags that categorize this link (e.g. "ai", "python", "tutorial", "tool", "research").

Respond with ONLY valid JSON, no markdown, no explanation.

URL: {url}
Original Title: {title}
Description: {description}"""


def _get_litellm():
    """Lazy import litellm to avoid blocking app startup."""
    import litellm
    litellm.suppress_debug_info = True
    return litellm


async def enrich_link(
    url: str,
    title: str | None,
    description: str | None,
    provider: str,
    model: str,
    api_key: str,
    ollama_base_url: str | None = None,
) -> dict | None:
    """Call the LLM to enrich a stash link with title, summary, and tags.

    Returns dict with keys: title, summary, tags — or None on failure.
    """
    prompt = ENRICHMENT_PROMPT.format(
        url=url,
        title=title or "(none)",
        description=description or "(none)",
    )

    try:
        litellm = _get_litellm()

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.3,
            "api_key": api_key,
        }

        # OpenAI and Google support response_format for JSON
        if provider in ("openai", "google"):
            kwargs["response_format"] = {"type": "json_object"}

        # Ollama needs a custom base URL
        if provider == "ollama":
            kwargs["api_base"] = ollama_base_url or "http://localhost:11434"

        response = await litellm.acompletion(**kwargs)
        finish_reason = response.choices[0].finish_reason
        content = response.choices[0].message.content or ""
        content = content.strip()
        print(f"[StashAI] finish_reason={finish_reason} len={len(content)} for {url}: {content}", flush=True)

        # Parse JSON response — handle potential markdown wrapping
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        # Try to extract JSON object if there's extra text around it
        if not content.startswith("{"):
            start = content.find("{")
            if start != -1:
                content = content[start:]
        if not content.endswith("}"):
            end = content.rfind("}")
            if end != -1:
                content = content[:end + 1]

        # Fix common JSON issues from LLMs
        # Replace single quotes with double quotes (common Gemini issue)
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try fixing common issues: trailing commas, single quotes
            import re
            fixed = re.sub(r',\s*}', '}', content)  # trailing commas
            fixed = re.sub(r',\s*]', ']', fixed)  # trailing commas in arrays
            result = json.loads(fixed)

        # Validate and sanitize
        enriched = {}
        if "title" in result and isinstance(result["title"], str):
            enriched["title"] = result["title"][:500]
        if "summary" in result and isinstance(result["summary"], str):
            enriched["summary"] = result["summary"][:1000]
        if "tags" in result and isinstance(result["tags"], list):
            enriched["tags"] = [
                str(t).lower().strip()[:100]
                for t in result["tags"][:10]
                if isinstance(t, str)
            ]

        return enriched if enriched else None

    except json.JSONDecodeError as e:
        logger.warning(f"AI enrichment returned invalid JSON for {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"AI enrichment failed for {url}: {e}")
        return None
