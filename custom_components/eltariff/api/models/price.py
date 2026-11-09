"""Price dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .vat import inclusive_price


@dataclass(frozen=True)
class Price:
    price_ex_vat: float
    price_inc_vat: float
    currency: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Price:
        price_ex_vat = float(d["priceExVat"])
        raw_inc = d.get("priceIncVat")
        return cls(
            price_ex_vat=price_ex_vat,
            price_inc_vat=float(raw_inc) if raw_inc is not None else inclusive_price(price_ex_vat),
            currency=d["currency"],
        )
