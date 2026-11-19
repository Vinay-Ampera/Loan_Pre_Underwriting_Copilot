"""AI control (Stage 10 add-on): the model, key status, prompts and safe settings the admin may
change from the browser, and how the running pipeline picks them up.

What is editable and what is not
  - Models: per role a primary model and ordered fallbacks, chosen from the providers listed in
    `llm_models.yaml` (a fixed catalogue); the router's retries, timeout and cooldown.
  - Settings: the model switch (off = code writes the report text), temperature and an output
    token limit per role.
  - Prompts: the **editable part** of each of the six prompts (its role and style). The **locked
    part** (data is not instructions, no arithmetic, "recommended" wording, no protected
    attributes, the reply format) always comes from the file in git and is appended after the
    editable part. A prompt can never be published without its locked part.
  - Not here, ever: scoring weights, bands, hard rules, the age cap, masking, the output schemas
    and guardrails, and the API keys (keys stay in `.env`; only their status is shown).

How a run uses it
  Every version is a row in the database (append-only; a rollback is a new version). When a case
  run starts, the runner binds the then-active `Snapshot` to that run (a context variable), so a
  change made while a case is running affects only the cases that start after it. With no
  database rows everything is the file default, exactly as before this feature.
"""

import asyncio
import hashlib
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import ProgrammingError

from app.core.config import Settings, get_settings

log = logging.getLogger("loan_copilot.ai_config")
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
CONFIG_PATH = Path(__file__).with_name("llm_models.yaml")
MARKER = "<!-- locked -->"
PROMPT_NAMES = ("supervisor", "extraction", "kyc", "risk", "policy", "decision")
ROLES = ("supervisor", "extraction", "decision", "kyc", "risk", "policy", "judge")
MAX_PROMPT_CHARS = 4000
MAX_FALLBACKS = 3
LIMITS = {
    "temperature": (0.0, 1.0),
    "max_tokens": (200, 8000),
    "num_retries": (0, 3),
    "timeout": (10, 300),
    "cooldown_time": (5, 300),
}
ROLE_LABELS = {
    "supervisor": "Supervisor: opens the case and writes the briefing",
    "extraction": "Extraction: fills fields the local reader could not",
    "decision": "Decision: writes the report summary",
    "kyc": "KYC: explains identity checks",
    "risk": "Risk: explains income, credit and behaviour",
    "policy": "Policy: cites policy clauses",
    "judge": "Judge: a second model that grades the report text",
}


# --------------------------------------------------------------------------- the file defaults
@dataclass(frozen=True)
class FilePrompt:
    name: str
    editable: str
    locked: str
    version: int


def file_prompt(name: str) -> FilePrompt:
    if name not in PROMPT_NAMES:
        raise KeyError(name)
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    header, _, body = raw.partition("-->")
    version = int(header.split("version:")[1].split("|")[0].strip())
    editable, _, locked = body.partition(MARKER)
    if not locked.strip():
        raise ValueError(f"prompts/{name}.md has no locked part ({MARKER})")
    return FilePrompt(name, editable.strip(), locked.strip(), version)


def _yaml() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def catalogue() -> dict[str, dict[str, str]]:
    """The providers the admin may choose from: id -> model name and the setting of its key."""
    return {
        pid: {"model": p["model"], "key_setting": p["key"], "key_env": p["key"].upper()}
        for pid, p in _yaml()["providers"].items()
        if "mock_response" not in p
    }


def default_config() -> dict[str, Any]:
    y = _yaml()
    return {
        "roles": {
            role: {
                "primary": spec["primary"], "fallbacks": list(spec["fallbacks"]),
                "temperature": 0.0, "max_tokens": None,
            }
            for role, spec in y["roles"].items()
        },
        "router": dict(y["router"]),
        "llm_enabled": True,
    }  # fmt: skip


def key_status(settings: Settings) -> dict[str, bool]:
    """provider id -> is its key present in `.env`. Never the value."""
    out = {}
    for pid, p in catalogue().items():
        secret = getattr(settings, p["key_setting"], None)
        out[pid] = bool(secret is not None and secret.get_secret_value().strip())
    return out


def validate_config(
    cfg: Any, settings: Settings | None = None, *, require_keys: bool = True
) -> list[str]:
    """Reasons this configuration cannot be saved. Empty = fine."""
    cat = catalogue()
    problems: list[str] = []
    if not isinstance(cfg, dict) or set(cfg) != {"roles", "router", "llm_enabled"}:
        return ["The configuration must have roles, router and llm_enabled."]
    roles = cfg["roles"]
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        return [f"Every role must be set: {', '.join(ROLES)}."]
    if not isinstance(cfg["llm_enabled"], bool):
        problems.append("llm_enabled must be true or false.")
    have = key_status(settings or get_settings()) if require_keys else {}
    for role, spec in roles.items():
        if not isinstance(spec, dict) or set(spec) != {
            "primary",
            "fallbacks",
            "temperature",
            "max_tokens",
        }:
            problems.append(f"{role}: needs primary, fallbacks, temperature and max_tokens.")
            continue
        chain = [
            spec["primary"],
            *(spec["fallbacks"] if isinstance(spec["fallbacks"], list) else [None]),
        ]
        if any(p not in cat for p in chain):
            problems.append(f"{role}: every model must be one of the listed providers.")
            continue
        if len(set(chain)) != len(chain):
            problems.append(f"{role}: a model can appear only once in its chain.")
        if len(chain) - 1 > MAX_FALLBACKS:
            problems.append(f"{role}: at most {MAX_FALLBACKS} fallbacks.")
        if require_keys:
            for p in chain:
                if not have.get(p):
                    problems.append(
                        f"{role}: the key for {p} ({cat[p]['key_env']}) is not set in .env."
                    )
        t, m = spec["temperature"], spec["max_tokens"]
        lo, hi = LIMITS["temperature"]
        if isinstance(t, bool) or not isinstance(t, int | float) or not lo <= t <= hi:
            problems.append(f"{role}: temperature must be between {lo} and {hi}.")
        lo, hi = LIMITS["max_tokens"]
        if m is not None and (isinstance(m, bool) or not isinstance(m, int) or not lo <= m <= hi):
            problems.append(
                f"{role}: the output token limit must be empty or between {lo} and {hi}."
            )
    r = cfg["router"]
    if not isinstance(r, dict) or set(r) != {"num_retries", "timeout", "cooldown_time"}:
        problems.append("router: needs num_retries, timeout and cooldown_time.")
    else:
        for k, (lo, hi) in ((k, LIMITS[k]) for k in r):
            v = r[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                problems.append(f"router: {k} must be a whole number from {lo} to {hi}.")
    if not problems:  # the judge must be a different model from the one it grades (TESTING.md)
        by = {p: cat[p]["model"] for p in cat}
        if by[roles["judge"]["primary"]] == by[roles["decision"]["primary"]]:
            problems.append(
                "judge: must not be the same model as decision (it would grade itself)."
            )
    return problems


def effective_yaml(cfg: dict[str, Any]) -> dict[str, Any]:
    """The `llm_models.yaml` shape `build_router` reads, with this configuration applied."""
    y = _yaml()
    y["roles"] = {r: {"primary": s["primary"], "fallbacks": list(s["fallbacks"])}
                  for r, s in cfg["roles"].items()}  # fmt: skip
    y["router"] = dict(cfg["router"])
    return y


def diff_config(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What changed, in words an audit row can hold (provider ids and numbers only)."""
    out: dict[str, Any] = {}
    for role in ROLES:
        b, a = before["roles"][role], after["roles"][role]
        if b != a:
            out[role] = {"from": b, "to": a}
    for k in ("router", "llm_enabled"):
        if before[k] != after[k]:
            out[k] = {"from": before[k], "to": after[k]}
    return out


def newly_used(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    """Providers placed in a role's chain that were not in that role's chain before. These have
    not answered for that role yet, so they are tested before the change is saved."""
    out: set[str] = set()
    for role in ROLES:
        old = {before["roles"][role]["primary"], *before["roles"][role]["fallbacks"]}
        new = {after["roles"][role]["primary"], *after["roles"][role]["fallbacks"]}
        out |= new - old
    return out


# --------------------------------------------------------------------------- a bound snapshot
@dataclass
class Snapshot:
    """The configuration one run uses, fixed when the run starts."""

    config_version: int = 0  # 0 = the file defaults
    config: dict[str, Any] = field(default_factory=default_config)
    prompts: dict[str, tuple[str, int]] = field(default_factory=dict)  # name -> (editable, version)
    settings: Settings | None = None
    _router: Any = field(default=None, repr=False, compare=False)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.config["llm_enabled"])

    def tuning(self, role: str) -> tuple[float, int | None]:
        spec = self.config["roles"].get(role)
        if not spec:
            return 0.0, None
        return float(spec["temperature"]), spec["max_tokens"]

    def prompt(self, name: str) -> tuple[str, int]:
        """(the full system prompt, its version). The locked part is always the file's."""
        fp = file_prompt(name)
        editable, version = self.prompts.get(name, (fp.editable, fp.version))
        return f"{editable.strip()}\n\n{fp.locked}", version

    def prompt_versions(self) -> dict[str, int]:
        return {n: self.prompts.get(n, (None, file_prompt(n).version))[1] for n in PROMPT_NAMES}

    def router(self) -> Any:
        if self._router is None:
            from app.services.llm import build_router  # noqa: PLC0415 - llm imports this module

            self._router = build_router(self.settings or get_settings(),
                                        config=effective_yaml(self.config))  # fmt: skip
        return self._router


_active = Snapshot()
_bound: ContextVar[Snapshot | None] = ContextVar("ai_config_snapshot", default=None)
_stamp: tuple[int, tuple[tuple[str, int], ...]] | None = None


def active() -> Snapshot:
    """The snapshot bound to this run, else the one new runs will get."""
    return _bound.get() or _active


def bind(snapshot: Snapshot) -> None:
    _bound.set(snapshot)


def set_active(snapshot: Snapshot, stamp: Any = None) -> None:
    global _active, _stamp  # noqa: PLW0603 - one active configuration per process
    _active, _stamp = snapshot, stamp


def reset() -> None:
    """Back to the file defaults (tests)."""
    set_active(Snapshot())
    _bound.set(None)


def prompt_text(name: str) -> tuple[str, int]:
    return active().prompt(name)


# --------------------------------------------------------------------------- the database
def _stamp_of(conn: Connection) -> tuple[int, tuple[tuple[str, int], ...]]:
    version = conn.execute(
        text("SELECT COALESCE(max(version), 0) FROM ai_config_versions")
    ).scalar_one()
    rows = conn.execute(
        text("SELECT name, max(version) FROM ai_prompt_versions GROUP BY name ORDER BY name")
    )
    return int(version), tuple((str(n), int(v)) for n, v in rows)


def config_versions(conn: Connection) -> list[Any]:
    return list(conn.execute(text(
        """SELECT v.version, v.config, v.reason, v.source, v.rolled_back_to, v.created_at,
                  u.name AS by
           FROM ai_config_versions v LEFT JOIN users u ON u.id = v.created_by
           ORDER BY v.version DESC LIMIT 50""")))  # fmt: skip


def load(conn: Connection, settings: Settings | None = None) -> Snapshot:
    """The configuration new runs should use: the latest saved versions, else the file."""
    row = conn.execute(
        text("SELECT version, config FROM ai_config_versions ORDER BY version DESC LIMIT 1")
    ).first()
    cfg = default_config()
    version = 0
    if row is not None:
        saved = row.config
        if not validate_config(saved, require_keys=False):  # a damaged row is ignored, never used
            cfg, version = saved, int(row.version)
    prompts: dict[str, tuple[str, int]] = {}
    for r in conn.execute(text(
        """SELECT DISTINCT ON (name) name, version, body FROM ai_prompt_versions
           ORDER BY name, version DESC""")):  # fmt: skip
        if r.name in PROMPT_NAMES and r.body.strip():
            prompts[r.name] = (r.body, int(r.version))
    return Snapshot(version, cfg, prompts, settings)


def refresh(engine: Engine, settings: Settings | None = None) -> Snapshot:
    """Make the newest saved configuration the active one (only if it changed) and return it."""
    try:
        with engine.connect() as conn:
            stamp = _stamp_of(conn)
            if _stamp == stamp:
                return _active
            snap = load(conn, settings)
    except ProgrammingError:  # the tables are not there yet (run `python -m app.db.migrate`)
        log.warning("AI control tables are missing; using the file defaults until migrated")
        return _active
    set_active(snap, stamp)
    return snap


async def refresh_async(engine: Engine, settings: Settings | None = None) -> Snapshot:
    return await asyncio.to_thread(refresh, engine, settings)


# --------------------------------------------------------------------------- the router stand-in
class ConfiguredRouter:
    """Looks like a LiteLLM Router to the agents but forwards each call to the router of the
    configuration bound to the running case. Used only where the app builds its own router."""

    async def acompletion(self, *args: Any, **kwargs: Any) -> Any:
        return await active().router().acompletion(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:  # primary_models and the like
        return getattr(active().router(), name)


# --------------------------------------------------------------------------- testing a model
async def probe_provider(
    settings: Settings, provider: str, timeout: float = 30.0
) -> dict[str, Any]:
    """One tiny real call to this provider. Returns ok, latency and the error class only (an error
    message can carry a key fragment, so it is never returned or logged)."""
    import json  # noqa: PLC0415

    import litellm  # noqa: PLC0415

    cat = catalogue()
    if provider not in cat:
        return {"provider": provider, "ok": False, "error": "UnknownProvider", "latency_ms": 0}
    secret = getattr(settings, cat[provider]["key_setting"], None)
    key = None if secret is None else secret.get_secret_value()
    started = time.perf_counter()
    try:
        ask = 'Reply with exactly this JSON and nothing else: {"ok": true}'
        resp = await litellm.acompletion(
            model=cat[provider]["model"], api_key=key, timeout=timeout, max_tokens=60,
            temperature=0, messages=[{"role": "user", "content": ask}],
        )  # fmt: skip
        content = (
            (resp.choices[0].message.content or "").strip().strip("`").removeprefix("json").strip()
        )
        ok = json.loads(content).get("ok") is True
        err = "" if ok else "UnexpectedReply"
    except Exception as exc:  # noqa: BLE001 - any failure is a failed test; only the class is kept
        ok, err = False, type(exc).__name__
    return {"provider": provider, "ok": ok, "error": err,
            "latency_ms": round((time.perf_counter() - started) * 1000)}  # fmt: skip


def sha(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def validate_prompt_body(name: str, body: Any) -> list[str]:
    """Reasons this editable text cannot be saved as a draft. Empty = fine."""
    if name not in PROMPT_NAMES:
        return ["Unknown prompt."]
    if not isinstance(body, str) or not body.strip():
        return ["The prompt cannot be empty."]
    problems: list[str] = []
    if len(body) > MAX_PROMPT_CHARS:
        problems.append(f"The prompt is longer than {MAX_PROMPT_CHARS} characters.")
    if MARKER in body or "-->" in body or "<!--" in body:
        problems.append(
            "The text cannot contain comment markers; the locked rules are added by the system."
        )
    if "```" in body:
        problems.append("The text cannot contain code fences.")
    from app.intake import injection  # noqa: PLC0415

    if [p for p in injection.scan(body) if p != "FORCE_OUTCOME"]:
        problems.append("The text looks like an instruction to override the rules; remove it.")
    tags = {
        "supervisor": ("case",), "kyc": ("checks",), "risk": ("items",), "decision": ("report",),
        "policy": ("clauses", "results"), "extraction": ("document",),
    }[name]  # fmt: skip
    for t in tags:
        if f"<{t}>" in body or f"</{t}>" in body:
            problems.append(
                f"The text cannot contain the data tag <{t}>; it marks where the data goes."
            )
    return problems
