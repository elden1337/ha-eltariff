"""Spike script: fetch and pretty-print Göteborg Energi tariffs."""
import asyncio
import json
import sys
from pathlib import Path

import aiohttp

BASE_URL = "https://api.goteborgenergi.cloud/gridtariff/v0"
SAMPLES_DIR = Path(__file__).parent.parent / "samples"


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/info") as resp:
            info = await resp.json()
            print("=== /info ===")
            print(json.dumps(info, indent=2, ensure_ascii=False))

        async with session.get(f"{BASE_URL}/tariffs") as resp:
            tariffs = await resp.json()

        SAMPLES_DIR.mkdir(exist_ok=True)
        out = SAMPLES_DIR / "goteborg_tariffs.json"
        out.write_text(json.dumps(tariffs, indent=2, ensure_ascii=False))
        print(f"\nSaved {len(tariffs.get('tariffs', []))} tariffs to {out}")

        refs = {
            c.get("reference")
            for t in tariffs.get("tariffs", [])
            for group in ("fixedPrice", "energyPrice", "powerPrice")
            if group in t
            for c in t[group].get("components", [])
        }
        print(f"\nDistinct component references: {sorted(r for r in refs if r)}")


if __name__ == "__main__":
    asyncio.run(main())
