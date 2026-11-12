"""Transcript sidecars: external services that turn a video URL into a transcript.

A sidecar is a module that satisfies the ``Sidecar`` protocol below. Adding it
to ``SIDECARS`` makes it a ``sidecar`` value for summarizer.yaml, the CLI, the
HTTP API and Streamlit; the pipeline handles order, fallback and caching.
"""

from typing import Protocol

from ..exceptions import ConfigurationError
from . import transcriptfetch


class Sidecar(Protocol):
    """The plugin contract (modules satisfy protocols for type checkers)."""

    LABEL: str

    @staticmethod
    def fetch(url: str, config: dict) -> list[tuple[float, str]]:
        """Return ``[(start_seconds, text), ...]`` or raise a ``SummarizerError``."""
        ...


SIDECARS: dict[str, Sidecar] = {"transcriptfetch": transcriptfetch}
SIDECAR_CHOICES = ("none", *SIDECARS)
SIDECAR_ORDERS = ("fallback", "first")


def resolve_sidecar(settings):
    """Return the validated (sidecar, order) from a runtime config or YAML defaults."""
    sidecar = str(settings.get("sidecar") or "none").strip().lower()
    order = str(settings.get("sidecar_order") or "fallback").strip().lower()
    if sidecar not in SIDECAR_CHOICES:
        raise ConfigurationError(
            f"Unknown sidecar {sidecar!r}; use one of: {', '.join(SIDECAR_CHOICES)}"
        )
    if order not in SIDECAR_ORDERS:
        raise ConfigurationError(
            f"Unknown sidecar order {order!r}; use one of: {', '.join(SIDECAR_ORDERS)}"
        )
    return sidecar, order
