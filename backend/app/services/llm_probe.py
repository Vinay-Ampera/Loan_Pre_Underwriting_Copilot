"""Probe the four LLM providers: `python -m app.services.llm_probe [--model-filter text]`.

Lists models each key can see, makes one tiny chat call per candidate model, and prints
rate-limit headers when the provider sends them. Prints no keys and no prompts' content.
"""

import argparse
import time

import httpx

from app.core.config import get_settings

PING = "Reply with the single word: ok"
INTERESTING = ("flash", "gpt-oss", "nemotron", ":free")
RL_PREFIXES = ("x-ratelimit", "retry-after")


def _rl(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower().startswith(RL_PREFIXES)}


def _show(label: str, r: httpx.Response, t0: float) -> None:
    ms = int((time.time() - t0) * 1000)
    extra = _rl(r.headers)
    err = ""
    if r.status_code >= 400:
        err = " " + r.text[:160].replace("\n", " ")
    print(f"  {label}: HTTP {r.status_code} {ms}ms {extra if extra else ''}{err}")


def probe_gemini(client: httpx.Client, key: str, flt: str, only: list[str]) -> None:
    print("GEMINI")
    h = {"x-goog-api-key": key}
    r = client.get(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers=h
    )
    if r.status_code != 200:
        print(f"  list: HTTP {r.status_code}")
        return
    names = [
        m["name"].removeprefix("models/")
        for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
        and "flash" in m["name"]
        and flt in m["name"]
    ]
    print("  flash models:", ", ".join(sorted(names)))
    for name in only or sorted(names)[:6]:
        if any(x in name for x in ("image", "tts", "live", "audio", "robotics", "computer")):
            continue
        t0 = time.time()
        body = {"contents": [{"parts": [{"text": PING}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent"
        _show(name, client.post(url, headers=h, json=body), t0)


def probe_openai_style(
    client: httpx.Client, label: str, base: str, key: str, models: list[str], flt: str
) -> None:
    print(label)
    h = {"Authorization": f"Bearer {key}"}
    r = client.get(f"{base}/models", headers=h)
    if r.status_code != 200:
        print(f"  list: HTTP {r.status_code}")
        return
    ids = sorted(m["id"] for m in r.json().get("data", []))
    shown = [i for i in ids if any(w in i.lower() for w in INTERESTING) and flt in i]
    print("  relevant models:", ", ".join(shown[:40]) or "(none)")
    for m in models:
        t0 = time.time()
        body = {"model": m, "messages": [{"role": "user", "content": PING}], "max_tokens": 200}
        _show(m, client.post(f"{base}/chat/completions", headers=h, json=body), t0)


def _l(v: str) -> list[str]:
    return [x for x in v.split(",") if x]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-filter", default="")
    ap.add_argument("--gemini", default="", help="comma list of Gemini model ids to call")
    ap.add_argument("--nvidia", default="", help="comma list of NVIDIA model ids to call")
    ap.add_argument("--openrouter", default="", help="comma list of OpenRouter ids to call")
    args = ap.parse_args()
    s = get_settings()
    with httpx.Client(timeout=60) as c:
        if s.gemini_api_key:
            probe_gemini(c, s.gemini_api_key.get_secret_value(), args.model_filter, _l(args.gemini))
        if s.groq_api_key:
            probe_openai_style(
                c, "GROQ", "https://api.groq.com/openai/v1",
                s.groq_api_key.get_secret_value(), ["openai/gpt-oss-20b"], args.model_filter,
            )  # fmt: skip
        if s.nvidia_api_key:
            probe_openai_style(
                c, "NVIDIA", "https://integrate.api.nvidia.com/v1",
                s.nvidia_api_key.get_secret_value(), _l(args.nvidia), args.model_filter,
            )  # fmt: skip
        if s.openrouter_api_key:
            probe_openai_style(
                c, "OPENROUTER", "https://openrouter.ai/api/v1",
                s.openrouter_api_key.get_secret_value(), _l(args.openrouter), args.model_filter,
            )  # fmt: skip


if __name__ == "__main__":
    main()
