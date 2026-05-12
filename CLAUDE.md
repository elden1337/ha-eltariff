# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
.venv/bin/python -m pytest tests/

# Run a single test file
.venv/bin/python -m pytest tests/test_billing.py -v

# Run a single test
.venv/bin/python -m pytest tests/test_billing.py::TestPeakTrackerCapacity::test_at_capacity_higher_than_min_replaces -v

# Lint
.venv/bin/ruff check custom_components/ tests/

# Lint + auto-fix
.venv/bin/ruff check --fix custom_components/ tests/
```

## Architecture

This is a Home Assistant custom integration (`custom_components/eltariff/`) that fetches Swedish DSO grid tariff data from a REST API and exposes it as HA sensors.

### Data flow

```
API (REST) → TariffApiClient → TariffCollection (cached)
                                      ↓
                            EltariffCoordinator (DataUpdateCoordinator)
                              - polls /info every ~12h (with jitter)
                              - fetches /tariffs only when tariffDataLastUpdated changes
                              - recomputes ActiveTariffSnapshot every 60s from cached data
                                      ↓
                            EltariffCoordinatorData
                              .snapshot   → sensors read this
                              .collection → used for schedule resolution
                              .next_transition → NextTransitionSensor
```

### API models (`api/models/`)

All API models are frozen dataclasses with `from_dict(d)` class methods — **no mutable state, no HA dependencies**. This makes them fully unit-testable without any HA fixtures. Key types:

- `Tariff` — top-level tariff with `valid_period`, `fixed_price`, `energy_price`, `power_price` (each a `PriceGroup`)
- `PriceComponent` — a single price component with a `Price` value object (`price_ex_vat`, `price_inc_vat`, `currency`)
- `ActiveTariffSnapshot` — the resolved view of which components are active right now; this is what sensors consume
- `ValidPeriod` — value object with `from_including: date` and `to_excluding: date | None`

### Billing layer (`billing/`)

Stateful, but also HA-free and fully unit-testable. Three modules:

- `iso_duration.py` — pure functions: `parse_iso_duration`, `period_start`, `period_end`, `is_same_period`. All period boundaries are calendar-aligned (P1M → first of month, P3M → quarters, P1Y → Jan 1).
- `peak_tracker.py` — `PeakTracker` keeps the top-N peaks across a billing period (one peak per identification period). `observed_peak` = min of stored peaks (the floor the customer has already committed to). `charged_peak` is derived via `peak_function` (average/maximum/minimum).
- `cost_service.py` — `CostService` orchestrates everything. Fed energy readings via `on_energy_update`; queried via `get_breakdown`. Fixed costs are returned as a lump sum for the billing period (annual/N, where N depends on billing period length) — not prorated mid-period.

### Async and HA integration

The coordinator and sensors are async HA components. `CostService` and `PeakTracker` are synchronous — they are called from within the async sensor property accessors, which is fine since they do no I/O. `RunningCostSensor` uses `RestoreEntity` to persist `CostService` state across HA restarts via `extra_state_attributes`.

### Config flow

Two-step setup: (1) select DSO from `KNOWN_DSOS`, (2) select tariff (labels include validity period to disambiguate same-name tariffs). Options flow allows reconfiguring VAT mode, bearer token, and energy sensor without re-setup. If a tariff ID expires, the coordinator auto-switches to the latest tariff with the same name.

### VAT mode

`"inc_vat"` / `"ex_vat"` is threaded through `CostService` via `vat_mode` property and applied at every price read. No price values are stored pre-VAT-adjusted.

### Testing

Tests live in `tests/`. The split is intentional:
- `test_models_unit.py` — all API model dataclasses, no fixtures needed
- `test_billing.py` — `PeakTracker` and `CostService`, including P1D peak replacement logic
- `test_schedule.py` / `test_schedule_advanced.py` — schedule resolution (active period matching, calendar patterns)
- `test_models.py` — integration smoke tests against real sample JSON (skipped if `samples/` not populated; run `scripts/dump_tariff.py` first)

`asyncio_mode = "auto"` is set globally in `pyproject.toml`, so async test functions work without decorators.
