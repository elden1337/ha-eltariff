# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

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

All 187 tests must pass and ruff must report no errors before a PR is merged.

## Architecture

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

### Key invariants

- **API models** (`api/models/`) are frozen dataclasses. No HA imports, no mutable state, no I/O. Every model has a `from_dict(d)` classmethod. Do not make them mutable.
- **Billing layer** (`billing/`) is synchronous and HA-free. `CostService` and `PeakTracker` are called from async sensor property accessors — keep them I/O-free.
- **Sensors** read from `ActiveTariffSnapshot` (resolved once per coordinator cycle). Never compute tariff logic inside a sensor.
- **VAT mode** (`"inc_vat"` / `"ex_vat"`) is applied at read time via `CostService.vat_mode`. Prices are never stored pre-adjusted.

## Layer rules

| Layer | May import | Must not import |
|---|---|---|
| `api/models/` | stdlib only | HA, billing |
| `billing/` | stdlib, `api/models/` | HA |
| `coordinator.py`, `sensor/`, etc. | anything | — |

## Testing

Tests live in `tests/`. Match the existing split:

| File | What it covers |
|---|---|
| `test_models_unit.py` | API model dataclasses — no fixtures needed |
| `test_billing.py` | `PeakTracker` and `CostService` |
| `test_schedule.py` / `test_schedule_advanced.py` | Schedule resolution, calendar pattern matching |
| `test_models.py` | Integration smoke tests against real sample JSON (skipped if `samples/` is empty) |

`asyncio_mode = "auto"` is set globally — async test functions work without decorators.

Write tests for any new billing logic or API model behaviour. Pure unit tests (no HA fixtures) are preferred.

To run the integration smoke tests, populate `samples/` first:

```bash
python scripts/dump_tariff.py
```

## Pull requests

- One logical change per PR.
- If you add a sensor, add a test for the value it exposes.
- If you change serialisation (e.g. `CostServiceState`), ensure old persisted state still deserialises without error.
- Update `README.md` if user-visible behaviour changes.

## For agents

- Read `CLAUDE.md` for architecture detail and the full command reference before making changes.
- Run the full test suite after every non-trivial edit: `.venv/bin/python -m pytest tests/ -q`
- Do not add `frozen=False` to API model dataclasses — they are intentionally immutable.
- Do not introduce HA imports into `api/models/` or `billing/`.
- Prefer editing existing files over creating new ones.
- Do not add comments that describe what the code does — only add comments for non-obvious *why*.
