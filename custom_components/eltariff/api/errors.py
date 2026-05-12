"""API error types for the eltariff integration."""

from __future__ import annotations


class TariffApiError(Exception):
    """Base error for API communication failures."""


class TariffApiAuthError(TariffApiError):
    """Raised when the server returns 401/403."""
