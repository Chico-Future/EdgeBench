from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class CloudModelConfig:
    key: str
    provider: str
    model: str
    base_url: str
    api_key_env: str
    enabled: bool
    supported_profiles: tuple[str, ...]
    temperature: float | None
    request_timeout: float
    max_tokens_field: str
    max_context_len: int
    max_new_tokens: dict[str, int]
    extra_body: dict[str, Any]
    seed: int | None


def load_environment(path: Path | None) -> None:
    if path is None:
        return
    if path.is_file():
        load_dotenv(path, override=False)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_mapping")
    return value


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    catalog = _mapping(value, "models_yaml")
    if catalog.get("version") != 1:
        raise ValueError("unsupported_models_yaml_version")
    _mapping(catalog.get("provider"), "provider")
    _mapping(catalog.get("defaults", {}), "defaults")
    _mapping(catalog.get("models"), "models")
    return catalog


def model_keys(path: Path, *, enabled_only: bool = False) -> list[str]:
    models = load_catalog(path)["models"]
    keys = []
    for key, value in models.items():
        item = _mapping(value, f"model_{key}")
        if not enabled_only or bool(item.get("enabled", False)):
            keys.append(str(key))
    return keys


def resolve_model(
    path: Path,
    key: str,
    *,
    env_file: Path | None,
    profile: str,
    interface: str,
    require_credentials: bool = True,
) -> CloudModelConfig:
    load_environment(env_file)
    catalog = load_catalog(path)
    provider = catalog["provider"]
    defaults = catalog.get("defaults", {})
    models = catalog["models"]
    if key not in models:
        raise KeyError(f"unknown_model_key:{key}")
    item = _mapping(models[key], f"model_{key}")

    model = str(item.get("model", "")).strip()
    if not model or model.startswith("REPLACE_WITH_"):
        raise ValueError(f"model_id_not_configured:{key}")
    provider_name = str(item.get("provider", provider.get("name", "openai_compatible"))).strip()
    base_url_env = str(
        item.get("base_url_env", provider.get("base_url_env", "OPENAI_BASE_URL"))
    )
    api_key_env = str(
        item.get("api_key_env", provider.get("api_key_env", "OPENAI_API_KEY"))
    )
    base_url = os.environ.get(base_url_env, "").strip()
    if not base_url:
        raise RuntimeError(f"missing_environment_variable:{base_url_env}")
    if "<WorkspaceId>" in base_url or "{WorkspaceId}" in base_url:
        raise RuntimeError(f"placeholder_environment_variable:{base_url_env}")
    if require_credentials and not os.environ.get(api_key_env, "").strip():
        raise RuntimeError(f"missing_environment_variable:{api_key_env}")

    supported = tuple(item.get("supported_profiles", defaults.get("supported_profiles", [])))
    if profile not in supported:
        raise ValueError(f"profile_not_supported:{key}:{profile}")
    if interface not in {"State-Given", "State-Seeking"}:
        raise ValueError(f"unsupported_interface:{interface}")

    max_new_tokens = dict(defaults.get("max_new_tokens", {}))
    max_new_tokens.update(item.get("max_new_tokens", {}))
    if interface not in max_new_tokens:
        raise ValueError(f"max_new_tokens_missing:{key}:{interface}")
    extra_body = dict(defaults.get("extra_body", {}))
    extra_body.update(item.get("extra_body", {}))

    raw_temperature = item.get("temperature", defaults.get("temperature", 0.0))
    temperature = None if raw_temperature is None else float(raw_temperature)

    return CloudModelConfig(
        key=key,
        provider=provider_name,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        enabled=bool(item.get("enabled", defaults.get("enabled", False))),
        supported_profiles=supported,
        temperature=temperature,
        request_timeout=float(item.get("request_timeout", defaults.get("request_timeout", 900))),
        max_tokens_field=str(item.get("max_tokens_field", defaults.get("max_tokens_field", "max_tokens"))),
        max_context_len=int(item.get("max_context_len", defaults.get("max_context_len", 16384))),
        max_new_tokens={name: int(value) for name, value in max_new_tokens.items()},
        extra_body=extra_body,
        seed=item.get("seed", defaults.get("seed")),
    )
