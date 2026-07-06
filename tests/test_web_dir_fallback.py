"""The dashboard must render on a fresh clone. static/ is gitignored, so serve
falls back to the committed web/dist; only if neither exists is it None."""
import os
from helicon.api.app import _resolve_web_dir


def _mk(root, name):
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "assets"))
    open(os.path.join(d, "index.html"), "w").close()
    return d


def test_prefers_static_when_present(tmp_path):
    root = str(tmp_path)
    _mk(root, "static")
    _mk(root, os.path.join("web", "dist"))
    assert _resolve_web_dir(root) == os.path.join(root, "static")


def test_falls_back_to_web_dist_on_fresh_clone(tmp_path):
    root = str(tmp_path)
    _mk(root, os.path.join("web", "dist"))          # no static/ — a fresh clone
    assert _resolve_web_dir(root) == os.path.join(root, "web", "dist")


def test_none_when_neither_built(tmp_path):
    assert _resolve_web_dir(str(tmp_path)) is None


def test_ignores_a_dir_without_index_html(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "static", "assets"))   # assets but no index
    _mk(root, os.path.join("web", "dist"))
    assert _resolve_web_dir(root) == os.path.join(root, "web", "dist")
