import json
import os

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(__file__))
_LEGACY_CONFIG_FILE = os.path.join(_PACKAGE_ROOT, "config.json")


def helicon_home() -> str:
    return os.path.abspath(os.path.expanduser(
        os.environ.get("HELICON_HOME", "~/.helicon")
    ))


def default_config_file() -> str:
    return os.path.join(helicon_home(), "config.json")


# Kept as a public compatibility seam for tests and callers that monkeypatch it.
CONFIG_FILE = os.environ.get("HELICON_CONFIG") or default_config_file()
_INITIAL_CONFIG_FILE = CONFIG_FILE


def config_file() -> str:
    """Current config path: explicit env, user home, then legacy checkout."""
    explicit = os.environ.get("HELICON_CONFIG")
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    if CONFIG_FILE != _INITIAL_CONFIG_FILE:  # compatibility: monkeypatched path
        return CONFIG_FILE
    user_path = default_config_file()
    if os.path.exists(user_path):
        return user_path
    if os.path.exists(_LEGACY_CONFIG_FILE):
        return _LEGACY_CONFIG_FILE
    return user_path


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


# The endpoint an old config implied when it carried a qwen_api_key and no
# base URL. It is used for that one case only (see resolve_llm); a new config
# has no default vendor.
LEGACY_LLM_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

_LEGACY_KEY_SOURCES = ("config qwen_api_key", "QWEN_API_KEY env")
_LEGACY_URL_SOURCES = ("config qwen_base_url", "legacy default")


def _first(sources: list[tuple[str, str | None]]) -> tuple[str, str]:
    for name, value in sources:
        if value:
            return value, name
    return "", ""


def resolve_llm(config: dict | None) -> dict:
    """Where the model layer points, and why. Pure: reads the config dict and
    the environment, writes nothing, so it gives the same answer on a dict from
    load_config and on a hand-built one.

    Order for each setting: neutral config key, neutral env, old qwen_* config
    key, old QWEN_API_KEY env. A config that only has qwen_* keys resolves
    exactly as it did before the layer was renamed, including the endpoint an
    old key implied. Nothing else gets a default vendor: no endpoint means the
    model-judged features are off, and `reason` says which setting is missing.

    Never put the key in a message. `key_source` names where it came from.
    """
    cfg = config or {}
    env = os.environ
    # load_config folds QWEN_API_KEY into config["qwen_api_key"] and marks it,
    # so the source line stays true for a key that only lives in the env.
    file_legacy_key = "" if cfg.get("_qwen_api_key_from_env") else cfg.get("qwen_api_key")
    api_key, key_source = _first([
        ("config llm_api_key", cfg.get("llm_api_key")),
        ("HELICON_LLM_API_KEY env", env.get("HELICON_LLM_API_KEY")),
        ("config qwen_api_key", file_legacy_key),
        ("QWEN_API_KEY env", env.get("QWEN_API_KEY") or cfg.get("qwen_api_key")),
    ])
    base_url, url_source = _first([
        ("config llm_base_url", cfg.get("llm_base_url")),
        ("HELICON_LLM_BASE_URL env", env.get("HELICON_LLM_BASE_URL")),
        ("config qwen_base_url", cfg.get("qwen_base_url")),
    ])
    if not base_url and key_source in _LEGACY_KEY_SOURCES:
        base_url, url_source = LEGACY_LLM_BASE_URL, "legacy default"
    model, model_source = _first([
        ("config llm_model", cfg.get("llm_model")),
        ("HELICON_LLM_MODEL env", env.get("HELICON_LLM_MODEL")),
    ])
    # The old tier table (helicon.llm.MODELS, qwen_models) names one vendor's
    # models, so it applies only to an endpoint that came from the old keys.
    legacy = url_source in _LEGACY_URL_SOURCES
    has_model = bool(model or legacy
                     or (cfg.get("llm_models") or {}).get("default")
                     or (cfg.get("qwen_models") or {}).get("default"))

    if not base_url:
        if api_key:
            reason = ("a model key is set but no endpoint: set llm_base_url "
                      "(or HELICON_LLM_BASE_URL)")
        else:
            reason = ("no model configured: set llm_base_url, llm_model and, if the "
                      "endpoint needs one, llm_api_key (or the HELICON_LLM_* env vars)")
        enabled = False
    elif not api_key and url_source in _LEGACY_URL_SOURCES:
        # An old init wrote the endpoint with an empty key slot. That was off
        # before and it stays off.
        reason = "no model key: set llm_api_key (or HELICON_LLM_API_KEY)"
        enabled = False
    elif not has_model:
        reason = "no model name: set llm_model (or HELICON_LLM_MODEL)"
        enabled = False
    else:
        reason = f"model endpoint configured ({url_source})"
        enabled = True
    return {
        "enabled": enabled, "reason": reason,
        "api_key": api_key, "key_source": key_source,
        "base_url": base_url, "base_url_source": url_source,
        "model": model, "model_source": model_source,
        "legacy": legacy,
    }


def load_config(path: str | None = None) -> dict:
    # Resolve at call time. `helicon demo` sets HELICON_CONFIG immediately
    # before uvicorn starts, while normal installs prefer ~/.helicon and retain
    # legacy checkout compatibility through config_file().
    config_path = os.path.abspath(os.path.expanduser(path)) if path else config_file()
    if not os.path.exists(config_path):
        # An EXPLICIT config that is not there is an error, not an empty config.
        # Returning {} silently made `HELICON_CONFIG=config-demo.json helicon
        # serve` (the README's own line) fall back to the default db_path,
        # CREATE an empty database and report {"status":"ok","cubes":0} — a
        # memory-integrity tool vouching for a store it had just invented. Say
        # it instead.
        explicit = path or os.environ.get("HELICON_CONFIG")
        if explicit:
            raise FileNotFoundError(
                f"config not found: {config_path}\n"
                f"  (HELICON_CONFIG points at a file that does not exist)\n"
                f"  demo:        helicon demo\n"
                f"  your stack:  helicon init")
        return {}
    with open(config_path) as f:
        config = json.load(f)

    config["db_path"] = expand_path(config.get("db_path", "data/helicon.db"))
    # Old key, old env. Kept as it was so a config that only has qwen_* keys
    # behaves exactly as before. The neutral llm_* keys and HELICON_LLM_* env
    # are read by resolve_llm at call time, and they win over these.
    if not config.get("qwen_api_key") and os.environ.get("QWEN_API_KEY"):
        config["_qwen_api_key_from_env"] = True
    config["qwen_api_key"] = config.get("qwen_api_key") or os.environ.get("QWEN_API_KEY", "")
    # Same shape as every other key: config.json first, env as the fallback.
    # judge_bench used to read OPENROUTER_API_KEY from the environment and
    # nowhere else, which made it the only component that could not be
    # configured the way the whole rest of the tool is. The field was not even
    # declared in config.example.json, so there was no way to discover that it
    # belonged there.
    config["openrouter_api_key"] = config.get("openrouter_api_key") or \
        os.environ.get("OPENROUTER_API_KEY", "")

    for name, conn in config.get("connectors", {}).items():
        for key in ("jsonl_dir", "memory_dir", "sessions_index", "vault_path", "repos_dir"):
            if key in conn:
                conn[key] = expand_path(conn[key])

    return config
