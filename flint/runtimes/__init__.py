"""Runtime adapters — per-runtime deploy specifics (image, templates, ports).

See ``base.py`` for the RuntimeAdapter protocol and ``registry.py`` to resolve
a runtime name to its adapter.
"""

from flint.runtimes.base import RuntimeAdapter as RuntimeAdapter
from flint.runtimes.registry import get_adapter as get_adapter
from flint.runtimes.registry import supported_runtimes as supported_runtimes
