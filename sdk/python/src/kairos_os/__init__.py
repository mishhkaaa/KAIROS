"""kairos-os: the Python client and command line for KAIROS, the operating system for organizational AI.

    from kairos_os import Kairos
    m = Kairos("http://localhost:8089")
    task = m.ask("Why is Project Apollo over budget?")
"""
from __future__ import annotations

__version__ = "0.1.0"

from .client import Kairos, KairosError  # noqa: E402

__all__ = ["Kairos", "KairosError", "__version__"]
