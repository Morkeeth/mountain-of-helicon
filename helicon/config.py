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
                f"  demo store:  python3 scripts/demo_seed.py\n"
                f"  your stack:  helicon init")
        return {}
    with open(config_path) as f:
        config = json.load(f)

    config["db_path"] = expand_path(config.get("db_path", "data/helicon.db"))
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
