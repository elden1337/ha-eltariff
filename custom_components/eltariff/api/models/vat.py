"""VAT fallback used when an API price omits the inclusive amount."""


def inclusive_price(price_ex_vat: float) -> float:
    """Estimate Swedish VAT at 25%, consistent with price curves."""
    return round(price_ex_vat * 1.25, 6)
