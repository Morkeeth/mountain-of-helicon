import json
import os

CONFIG_FILE = os.environ.get("HELICON_CONFIG") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config.json")


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def load_config(path: str | None = None) -> dict:
    config_path = path or CONFIG_FILE
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
                f"  your stack:  helicon init   (or cp config.example.json config.json)")
        return {}
    with open(config_path) as f:
        config = json.load(f)

    config["db_path"] = expand_path(config.get("db_path", "data/helicon.db"))
    config["qwen_api_key"] = config.get("qwen_api_key") or os.environ.get("QWEN_API_KEY", "")

    for name, conn in config.get("connectors", {}).items():
        for key in ("jsonl_dir", "memory_dir", "sessions_index", "vault_path", "repos_dir"):
            if key in conn:
                conn[key] = expand_path(conn[key])

    return config
