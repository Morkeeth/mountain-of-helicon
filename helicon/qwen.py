"""Compatibility shim. The model layer lives in helicon.llm.

Helicon was born on one vendor's endpoint and this module carried that name.
The layer is provider-neutral now, so the code moved to helicon/llm.py. Every
`from helicon.qwen import ...` and every `helicon.qwen.<name>` keeps working,
because this name resolves to the SAME module object as helicon.llm. A plain
re-export would give two modules with two copies of the cache, the call log
and the cache connection, and a monkeypatch on one would not reach the other.
"""
import sys

import helicon.llm as _llm

sys.modules[__name__] = _llm
