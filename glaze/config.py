import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


def expand_path(path: str) -> str:
    return os.path.expanduser(os.path.expandvars(path))


def load_config(path: str | None = None) -> dict:
    config_path = path or CONFIG_FILE
    if not os.path.exists(config_path):
        return {}
    with open(config_path) as f:
        config = json.load(f)

    config["db_path"] = expand_path(config.get("db_path", "data/glaze.db"))
    config["qwen_api_key"] = config.get("qwen_api_key") or os.environ.get("QWEN_API_KEY", "")

    for name, conn in config.get("connectors", {}).items():
        for key in ("jsonl_dir", "memory_dir", "sessions_index", "vault_path", "repos_dir"):
            if key in conn:
                conn[key] = expand_path(conn[key])

    return config
