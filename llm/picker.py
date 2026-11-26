"""Pick a niche-fitting story from trend candidates and write the script (Gemini)."""
import json
import re
import time
import requests

import config

TIMEOUT = 90
MAX_OUT, MIN_OUT = 4000, 1200   # output-token allowance bounds (the allowance shrinks when the prompt is large)


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def load_history():
    if config.HISTORY_FILE.exists():
        return json.loads(config.HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(h):
    config.HISTORY_FILE.write_text(json.dumps(h, indent=2), encoding="utf-8")


def dedupe(items, history):
    seen = {norm(h) for h in history}
    out, local = [], set()
    for it in items:
        n = norm(it["title"])
        if n and n not in seen and n not in local:
            local.add(n)
            out.append(it)
    return out


def build_prompt(items, niche, history):
    titles = "\n".join(f"- {i['title']}" for i in items)
    used = "\n".join(f"- {h}" for h in history[-30:]) or "(none)"
    return f"""You plan faceless 30-60 second vertical videos for the niche: {niche}.
Today's trending headlines (loose inspiration only):
{titles}

Already made, do not repeat:
{used}

Choose ONE video idea that fits the niche. A trend may inspire it, but the story must be
accurate, original in angle, and safe: no real private individuals, no graphic violence,
no medical/financial advice, no unverified claims presented as fact.
Return ONLY JSON with keys:
topic (short), hook (first spoken sentence, grabs attention in 2 seconds),
script (90-150 words, spoken narration, starts with the hook, no stage directions),
title (<= 70 chars), description, tags (list of 5-8), search_terms (list of 5 English
stock-footage keywords), fact_notes (list of the factual claims a human should verify).
"""


_cooldown = {}   # provider name -> unix time until which it is skipped (rate limited / failing)
_hard = set()    # providers that answered 401/402/403 (key or credits): skipped for this run


def parse_retry_after(text, default=30.0):
    """Seconds from messages like 'try again in 9.975s', '1m30.5s' or '2h3m1s'."""
    m = re.search(r"try again in ((?:\d+h)?(?:\d+m)?[\d.]*s?)", text or "")
    if not m or not m.group(1):
        return default
    t = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", m.group(1))
    if not t or not any(t.groups()):
        return default
    h, mi, sec = t.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec or 0)


def _usable(p):
    local = "localhost" in p["base"] or "127.0.0.1" in p["base"]
    return bool(p["key"]) or local


def _claude(p, model, prompt, max_tokens, on_progress):
    """Claude Messages API, streamed so the caller can show progress. -> (text, None) or (None, (kind, detail, wait))"""
    try:
        r = requests.post(f"{p['base']}/messages", stream=True, timeout=(15, 120),
                          headers={"x-api-key": p["key"], "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": max_tokens, "stream": True,
                                "messages": [{"role": "user", "content": prompt}]})
    except requests.RequestException as e:
        return None, ("retry", f"{type(e).__name__}", 20)
    if r.status_code == 429 or r.status_code >= 500:   # 529 = overloaded
        return None, ("retry", f"HTTP {r.status_code}: {r.text[:200]}", float(r.headers.get("retry-after", 20)))
    if r.status_code in (401, 402, 403):
        return None, ("hard", f"HTTP {r.status_code}: {r.text[:200]}", 0)
    if not r.ok:
        raise RuntimeError(f"Claude HTTP {r.status_code}: {r.text[:400]}")
    parts, shown = [], 0
    try:
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            t = ev.get("type")
            if t == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                parts.append(ev["delta"]["text"])
                n = sum(len(x) for x in parts)
                if on_progress and n - shown >= 300:
                    shown = n
                    on_progress(f"Claude has written {n:,} characters…")
            elif t == "error":
                err = ev.get("error", {})
                return None, ("retry", f"{err.get('type')}: {err.get('message', '')}", 20)
            elif t == "message_delta" and ev.get("delta", {}).get("stop_reason") == "max_tokens":
                raise RuntimeError("Claude ran out of room before finishing (max_tokens). Try fewer chapters.")
    except requests.RequestException as e:
        return None, ("retry", f"connection dropped ({type(e).__name__})", 10)
    text = "".join(parts)
    return (text, None) if text.strip() else (None, ("retry", "empty reply", 5))


def ask_llm(prompt, role="gen", on_progress=None):
    """Call an OpenAI-compatible /chat/completions endpoint, falling through the configured providers.

    role: "gen" uses each provider's generator model, "judge" its (different) judge model.
    On HTTP 429 or a server error the provider is put on cooldown and the next one is tried; when every
    provider is cooling down the call waits for the soonest one (max 60 s per wait) and tries again.
    Providers: LLM_* (first), LLM2_* and LLM3_* in .env, each a *different* service, not extra accounts.
    """
    providers = [p for p in config.providers() if _usable(p)]
    if not providers:
        raise RuntimeError("LLM_API_KEY is not set (put it in .env)")
    # Per-minute token limit (Groq free tier: 8000). A request is rejected outright (HTTP 413) when its prompt plus the
    # reserved output exceeds it, so size the output allowance to what the prompt leaves.
    est_in = int(len(prompt) / 3.4) + 60
    out_budget = min(MAX_OUT, config.TPM_LIMIT - est_in - 150)
    if out_budget < MIN_OUT:
        raise RuntimeError(f"prompt is about {est_in} tokens, too large for a {config.TPM_LIMIT} tokens-per-minute limit "
                           f"(needs room for {MIN_OUT}+ output tokens): give the models a shorter source text")
    last = ""
    for _ in range(12):
        if all(p["name"] in _hard for p in providers):   # every provider has a key/credit problem: waiting will not help
            raise RuntimeError(f"all LLM providers rejected the request (key or credits); last: {last}")
        now = time.time()
        ready = [p for p in providers if _cooldown.get(p["name"], 0) <= now]
        if not ready:
            wait = min(_cooldown[p["name"]] for p in providers) - now
            if on_progress:
                on_progress(f"Waiting {int(max(1, wait))} s for the AI service (rate limit)…")
            time.sleep(max(1.0, min(60.0, wait + 1)))
            continue
        for p in ready:
            model = p["judge"] if role == "judge" else p["gen"]
            if "anthropic.com" in p["base"]:   # Claude: native Messages API (its OpenAI layer rejects json_object/temperature)
                text, fail = _claude(p, model, prompt, max(out_budget, 8000), on_progress)
                if text is not None:
                    return text
                kind, detail, wait = fail
                last = f"{p['name']} {detail}"
                if kind == "hard":
                    _cooldown[p["name"]] = time.time() + 900
                    _hard.add(p["name"])
                else:
                    _cooldown[p["name"]] = time.time() + wait
                    if on_progress:
                        on_progress(f"Claude is busy ({detail[:60]}); trying again in {int(wait)} s…")
                continue
            body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}, "temperature": 0.7 if role == "gen" else 0.2,
                    "max_completion_tokens": out_budget}  # reasoning models spend part of this on hidden thinking
            if "gpt-oss" in model:
                body["reasoning_effort"] = "low"
            elif "qwen" in model.lower():
                body["reasoning_effort"] = "none"   # no long hidden thinking: it would eat the output budget
            try:
                r = requests.post(f"{p['base']}/chat/completions", timeout=TIMEOUT,
                                  headers={"Authorization": f"Bearer {p['key']}"}, json=body)
            except requests.RequestException as e:
                _cooldown[p["name"]] = time.time() + 30
                last = f"{p['name']}: {type(e).__name__}"
                continue
            if r.status_code == 429 or r.status_code >= 500:
                _cooldown[p["name"]] = time.time() + parse_retry_after(r.text)
                last = f"{p['name']} HTTP {r.status_code}: {r.text[:200]}"
                continue
            bigger = min(8000, config.TPM_LIMIT - est_in - 150)
            if r.status_code == 400 and "max completion tokens" in r.text and body["max_completion_tokens"] < bigger:
                body["max_completion_tokens"] = bigger   # a reasoning model used up its budget thinking: one bigger retry
                try:
                    r = requests.post(f"{p['base']}/chat/completions", timeout=TIMEOUT,
                                      headers={"Authorization": f"Bearer {p['key']}"}, json=body)
                except requests.RequestException as e:
                    _cooldown[p["name"]] = time.time() + 30
                    last = f"{p['name']}: {type(e).__name__}"
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    _cooldown[p["name"]] = time.time() + parse_retry_after(r.text)
                    last = f"{p['name']} HTTP {r.status_code}: {r.text[:200]}"
                    continue
            if r.status_code == 400 and "json_validate_failed" in r.text:   # the model wrote broken JSON: ask again
                last = f"{p['name']}: model returned invalid JSON"
                time.sleep(1.0)
                continue
            if r.status_code in (401, 402, 403):   # bad key or no credits on THIS provider: skip it, try the others
                _cooldown[p["name"]] = time.time() + 900
                _hard.add(p["name"])
                last = f"{p['name']} HTTP {r.status_code}: {r.text[:200]}"
                continue
            if not r.ok:  # a real client error (bad model name, ...): show it, do not hide it
                raise RuntimeError(f"LLM {p['name']} HTTP {r.status_code}: {r.text[:400]}")
            content = (r.json()["choices"][0].get("message") or {}).get("content")
            if not content or not str(content).strip():   # a reasoning model sometimes returns nothing: try again
                last = f"{p['name']}: empty reply"
                time.sleep(1.0)
                continue
            return content
    raise RuntimeError(f"all LLM providers rate limited or failing; last: {last}")


REQUIRED = ("topic", "script", "title", "description", "tags", "search_terms")


def parse_idea(text):
    data = json.loads(text)
    if isinstance(data, list):
        data = data[0]
    missing = [k for k in REQUIRED if not data.get(k)]
    if missing:
        raise ValueError(f"model response missing fields: {missing}")
    return data


def pick(items, history):
    fresh = dedupe(items, history)
    if not fresh:
        raise RuntimeError("no fresh trend candidates after dedupe")
    return parse_idea(ask_llm(build_prompt(fresh, config.NICHE, history)))
