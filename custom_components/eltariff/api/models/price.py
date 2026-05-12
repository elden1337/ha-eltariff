"""Price dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Price:
    price_ex_vat: float
    price_inc_vat: float
    currency: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Price:
        return cls(
            price_ex_vat=float(d["priceExVat"]),
            price_inc_vat=float(d["priceIncVat"]),
            currency=d["currency"],
        )
