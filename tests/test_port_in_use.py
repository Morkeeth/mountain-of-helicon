"""A server that cannot bind must not end with an invitation to open it.

THE BUG THIS PINS, found on the fifth cold clone. `helicon demo` with port 8420
already held printed:

    ERROR:  [Errno 48] error while attempting to bind ... address already in use
    INFO:   Application shutdown complete.
    Mountain of Helicon — demo
      open  http://127.0.0.1:8420/#findings
    Press Ctrl+C to stop

uvicorn's exit code was honest (3). The OUTPUT was not: uvicorn logs to stderr
unbuffered while those lines sit in a buffered stdout, so the LAST WORDS on the
screen were an invitation to open a URL that serves nothing, with the reason
scrolled off above. A stranger clicks the dead link and concludes the project is
broken — and that verdict never reaches us.
"""
import socket

import pytest

from helicon.cli import _refuse_if_port_taken


@pytest.fixture
def taken_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        yield held.getsockname()[1]


def test_a_taken_port_stops_the_command_before_it_invites_you(taken_port):
    with pytest.raises(SystemExit) as e:
        _refuse_if_port_taken("127.0.0.1", taken_port, "demo")
    assert e.value.code != 0


def test_the_message_names_the_port_and_two_ways_out(taken_port):
    with pytest.raises(SystemExit) as e:
        _refuse_if_port_taken("127.0.0.1", taken_port, "demo")

    message = str(e.value.code)
    assert str(taken_port) in message, "name the port that is actually blocked"
    assert "lsof" in message, "how to find out what is holding it"
    assert f"--port {taken_port + 1}" in message, "how to get past it right now"


def test_the_command_name_in_the_hint_is_the_one_you_ran(taken_port):
    """`helicon demo --port N` for demo, `helicon serve --port N` for serve.
    A hint that names the other command is a hint that has to be translated."""
    with pytest.raises(SystemExit) as e:
        _refuse_if_port_taken("127.0.0.1", taken_port, "serve")
    assert "helicon serve --port" in str(e.value.code)


def test_a_free_port_passes_silently():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    # closed above, so it is free again
    _refuse_if_port_taken("127.0.0.1", free, "serve")


def test_the_probe_does_not_hold_the_port_it_checked():
    """A guard that leaves its own listener behind would make the server it is
    protecting fail to bind — the check causing the failure it tests for."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]

    _refuse_if_port_taken("127.0.0.1", free, "serve")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as after:
        after.bind(("127.0.0.1", free))  # must not raise
