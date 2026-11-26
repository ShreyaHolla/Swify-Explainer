"""Settings from environment / .env (no extra dependency)."""
import os
from pathlib import Path

ROOT = Path(__file__).parent


def _load_env():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# Any OpenAI-compatible chat endpoint: Groq, OpenRouter, Cerebras, local Ollama...
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
TPM_LIMIT = int(os.getenv("LLM_TPM_LIMIT", "8000"))   # provider tokens-per-minute limit (Groq free tier: 8000)
LLM_JUDGE_MODEL =os.getenv("LLM_JUDGE_MODEL", "qwen/qwen3.8-27b")  # adversarial fact-checker: a different model family


def _extra(n):
    """Optional fallback provider n (2 or 3): a DIFFERENT service (OpenRouter, Cerebras, local Ollama...)."""
    base, model = os.getenv(f"LLM{n}_BASE_URL", "").rstrip("/"), os.getenv(f"LLM{n}_MODEL", "")
    if not (base and model):
        return None
    return {"name": f"llm{n}", "base": base, "key": os.getenv(f"LLM{n}_API_KEY", ""),
            "gen": model, "judge": os.getenv(f"LLM{n}_JUDGE_MODEL", model)}


def providers():
    """Ordered provider list; the first is used until it is rate limited, then the next."""
    ps = [{"name": "llm1", "base": LLM_BASE_URL, "key": LLM_API_KEY, "gen": LLM_MODEL, "judge": LLM_JUDGE_MODEL}]
    return ps + [p for p in (_extra(2), _extra(3)) if p]


NICHE = os.getenv("NICHE", "history mysteries and unexplained events")
HISTORY_FILE =ROOT / "history.json"
UA = {"User-Agent": "trend-pipeline/0.1 (personal project)"}
