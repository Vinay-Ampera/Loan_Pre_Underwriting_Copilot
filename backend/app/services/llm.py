"""LiteLLM wrapper: role -> model with fallback, output validated against a Pydantic schema.

Callers pass MASKED messages only (masking lives in app.intake, Stage 2). This module never
logs message content.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from litellm.router import Router
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings

CONFIG_PATH = Path(__file__).with_name("llm_models.yaml")


class LLMOutputError(Exception):
    """The model answered but not with JSON that fits the schema."""


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    model: str  # the deployment that actually answered (shows fallback use)
    tokens_in: int
    tokens_out: int


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open() as f:
        cfg: dict[str, Any] = yaml.safe_load(f)
    return cfg


def build_router(
    settings: Settings | None = None,
    config: dict[str, Any] | None = None,
    override_keys: dict[str, str] | None = None,
) -> Router:
    """One LiteLLM model group per role. `override_keys` lets tests break a provider on purpose."""
    s = settings or get_settings()
    cfg = config or load_config()
    providers: dict[str, dict[str, str]] = cfg["providers"]

    def key_for(provider: str) -> str | None:
        name = providers[provider]["key"]
        if override_keys and name in override_keys:
            return override_keys[name]
        secret = getattr(s, name)
        return None if secret is None else str(secret.get_secret_value())

    model_list: list[dict[str, Any]] = []
    fallbacks: list[dict[str, list[str]]] = []
    for role, spec in cfg["roles"].items():
        for rank, prov in enumerate([spec["primary"], *spec["fallbacks"]]):
            model_list.append(
                {
                    "model_name": role if rank == 0 else f"{role}__fb{rank}",
                    "litellm_params": {"model": providers[prov]["model"], "api_key": key_for(prov)},
                }
            )
        if spec["fallbacks"]:
            fallbacks.append({role: [f"{role}__fb{i + 1}" for i in range(len(spec["fallbacks"]))]})
    r = cfg["router"]
    return Router(
        model_list=model_list,
        fallbacks=fallbacks,
        num_retries=r["num_retries"],
        timeout=r["timeout"],
        cooldown_time=r["cooldown_time"],
    )


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


async def complete[T: BaseModel](
    router: Router,
    role: str,
    messages: list[dict[str, str]],
    schema: type[T],
    max_tokens: int = 2000,
) -> LLMResult[T]:
    """Call `role`, fall back on errors, validate the reply as `schema`. Raises LLMOutputError."""
    resp: Any = await router.acompletion(  # litellm's response types are loose; validated below
        model=role,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = resp.choices[0].message.content or ""
    try:
        output = schema.model_validate(_extract_json(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMOutputError(f"{role}: reply failed schema {schema.__name__}") from exc
    usage = getattr(resp, "usage", None)
    return LLMResult(
        output=output,
        model=str(resp.model),
        tokens_in=getattr(usage, "prompt_tokens", 0),
        tokens_out=getattr(usage, "completion_tokens", 0),
    )
