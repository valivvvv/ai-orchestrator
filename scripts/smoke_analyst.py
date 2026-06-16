"""
Smoke test for the Analyst agent (make_plan -> execute_step* -> synthesize).

Wraps the shared LLM so every prompt sent and every response received is
printed, making the context passed BETWEEN the LLM calls (planner ->
NL2SQL workers -> synthesize) visible end to end.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))

from dotenv import load_dotenv
load_dotenv()

from skillab import get_llm

from analyst_agent import AnalystAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")

DATA_DIR = Path(__file__).parent.parent / "data"

_PROVIDER_ALIASES = {"gemini": "google", "ollama": "local"}
_MODEL_ENV_VARS = {
    "google": "GOOGLE_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "openai": "OPENAI_MODEL",
    "local": "OLLAMA_MODEL",
}


def _resolve_provider(provider):
    return _PROVIDER_ALIASES.get(provider.lower(), provider.lower()) if provider else None


def _model_from_env(provider):
    resolved = _resolve_provider(provider)
    env_var = _MODEL_ENV_VARS.get(resolved, f"{resolved.upper()}_MODEL")
    return os.getenv("LLM_MODEL") or os.getenv(env_var)


class LoggingLLM:
    """Delegates to a real LLMProvider, printing each prompt and response."""

    def __init__(self, inner):
        self._inner = inner
        self._call_count = 0

    def generate_sync(self, messages, **kwargs):
        self._call_count += 1
        call_number = self._call_count
        print(f"\n{'#' * 78}")
        print(f"# LLM CALL {call_number} — PROMPT")
        print(f"{'#' * 78}")
        for message in messages:
            print(f"[{message['role']}]\n{message['content']}")
        response = self._inner.generate_sync(messages, **kwargs)
        print(f"\n{'-' * 78}")
        print(f"# LLM CALL {call_number} — RESPONSE")
        print(f"{'-' * 78}")
        print(response)
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


def main() -> int:
    provider = _resolve_provider(os.getenv("LLM_PROVIDER"))
    model = _model_from_env(os.getenv("LLM_PROVIDER"))
    llm = LoggingLLM(get_llm(provider=provider, model=model))
    print(f"Using LLM: {provider} / {llm.model}")

    analyst = AnalystAgent(
        tables_config={
            "achizitii_directe": {
                "schema_path": str(DATA_DIR / "nl2sql_agent" / "schema_achizitii_directe.json"),
                "business_path": str(DATA_DIR / "nl2sql_agent" / "business_achizitii_directe.json"),
            },
            "anunturi_initiere": {
                "schema_path": str(DATA_DIR / "nl2sql_agent" / "schema_anunturi_initiere.json"),
                "business_path": str(DATA_DIR / "nl2sql_agent" / "business_anunturi_initiere.json"),
            },
        },
        llm=llm,
    )

    question = "Care sunt top 5 furnizori după valoarea totală a contractelor?"
    print(f"\n=== QUESTION: {question} ===")
    result = analyst.chat(question)

    print(f"\n{'=' * 78}")
    print(f"status  : {result['status']}")
    print(f"answer  : {result['answer']}")

    if result["status"] != "success":
        print("\nFAIL: expected status=success")
        return 1

    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
