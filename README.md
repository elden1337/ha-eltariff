# ha-eltariff

A Home Assistant custom integration that exposes Swedish DSO (Distribution System Operator) grid tariffs as sensors. It complements spot-price integrations such as Nordpool or Tibber by covering the network charge side of your electricity bill — the part you pay your grid owner, not your electricity supplier.

## Supported DSOs

| DSO | Key |
|-----|-----|
| Göteborg Energi Nät AB | `goteborg_energi` |
| Tekniska Verken | `tekniska_verken` |
| Norrtälje Energi AB | `norrtalje_energi` |
| Skånska Energi Nät AB | `skanska_energi` |
| Kraftringen Nät AB | `kraftringen_nat` |

Any DSO that implements the RI-SE Grid Tariff API can also be connected via the "Custom URL" option in the configuration flow.

## Installation

1. In HACS, add this repository as a custom repository (category: Integration).
2. Install "Eltariff" and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for "Eltariff".

## Configuration

The setup flow has three steps:

1. **Pick DSO** — select your grid owner from the dropdown, or choose "Custom URL" and enter the API base URL. The integration validates the endpoint before proceeding.
2. **Pick tariff** — select your tariff from the list. The tariff currently valid today is listed first.
3. **Options** — choose whether sensor values should include or exclude VAT (`inc_vat` / `ex_vat`). Optionally enter a Bearer token if your DSO requires authentication.

## Sensors

Entity IDs are prefixed with the device name derived from your config entry (e.g. `sensor.goteborg_energi_nat_ab_sommartid_lag_active_power_band`). All entities for a given config entry are grouped under one device in the HA device registry.

| Entity | Unit | Description |
|--------|------|-------------|
| `…active_power_price` | SEK/kW | Price of the currently active power (effect) component |
| `…active_power_band` | — | Reference label of the active power band (e.g. `high`, `low`) |
| `…energy_price_total` | SEK/kWh | Sum of all active energy price components |
| `…energy_transfer_price` | SEK/kWh | The main energy transfer component (reference `main`) |
| `…energy_tax` | SEK/kWh | Energy tax component (reference `tax`) |
| `…fixed_price_annual` | SEK/year | Sum of all active fixed-price components |
| `…peaks_used_for_average` | peaks | Number of monthly peak hours used to calculate the effect tariff |
| `…next_tariff_transition` | timestamp | Next datetime when the active tariff band changes |
| `…high_tariff_active` | — | `on` when a peak-priced power component is active |

Each sensor exposes only the state attributes relevant to it. The `today_schedule` attribute (hourly slots with `start`, `end`, `band`, and `price_inc_vat`) is available on `energy_price_total`, `energy_transfer_price`, and `next_tariff_transition`.

## Using sensors in automations

### Avoid running high-load appliances during peak tariff hours

```yaml
automation:
  - alias: "Pause dishwasher during high tariff"
    trigger:
      - platform: state
        entity_id: binary_sensor.eltariff_high_tariff_active
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.dishwasher
```

### Pass today's schedule to advanced calculations and other integrations

The `today_schedule` attribute on `sensor.…energy_price_total` (or `…energy_transfer_price` / `…next_tariff_transition`) can be read in a template or passed to an automation that controls climate equipment:

```yaml
- variables:
    schedule: "{{ state_attr('sensor.my_dso_my_tariff_energy_price_total', 'today_schedule') }}"
```

## The 3-highest-hours peak rule (effekttariff)

Göteborg Energi Nät AB and several other Swedish DSOs charge for peak power based on the average of your three highest one-hour consumption peaks during a rolling month. The integration exposes this as `sensor.eltariff_peaks_used_for_average` — its value (typically `3`) is read directly from the tariff's `peakIdentificationSettings`.

The practical implication: if you can avoid adding a new "top-3 peak hour" in the current month, you save money. Automations that defer high-load appliances away from hours when `binary_sensor.eltariff_high_tariff_active` is `on` directly reduce the risk of creating a new peak.

## Known limitations

- **Catalogue API not implemented.** The RI-SE API spec includes an endpoint for looking up which DSO serves a given metering point (MPID). This integration does not use it — you must select your DSO manually.
- **`/prices` endpoint not consumed.** Some DSOs expose a `/prices` endpoint with time-varying energy prices. Most DSOs do not populate it yet, so this integration ignores it. Use Nordpool or Tibber for spot prices.
