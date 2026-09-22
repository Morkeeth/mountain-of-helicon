import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ["EVAL_REPO"]


def run(name):
    return subprocess.run(
        ["bash", os.path.join(REPO, "scripts", "check_data.sh"), os.path.join(HERE, "data", name)],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    ).returncode


def test_bad_file_fails():
    assert run("bad.json") != 0


def test_good_file_passes():
    assert run("good.json") == 0
