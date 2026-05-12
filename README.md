# ha-eltariff

A Home Assistant custom integration that exposes Swedish DSO (Distribution System Operator) grid tariffs as sensors. It complements spot-price integrations such as Nordpool or Tibber by covering the network charge side of the electricity bill — the part you pay your grid owner, not your electricity supplier.
The structure of Swedish grid tariffs is complex, with multiple price components that can vary by time of day, day of week, season, and total consumption. This integration implements the [RI-SE Grid Tariff API](https://github.com/RI-SE/Eltariff-API), which several DSOs have adopted to publish their tariffs in a structured way.

## Supported DSOs

| DSO | Key |
|-----|-----|
| Göteborg Energi Nät AB | `goteborg_energi` |
| Tekniska Verken | `tekniska_verken` |
| Norrtälje Energi AB | `norrtalje_energi` |
| Skånska Energi Nät AB | `skanska_energi` |
| Kraftringen Nät AB | `kraftringen_nat` |


## Installation

1. In HACS, add this repository as a custom repository (category: Integration).
2. Install "Eltariff" and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for "Eltariff".

## Configuration

The setup flow has three steps:

1. **Pick DSO** — select your grid owner from the dropdown. The integration validates the endpoint before proceeding.
2. **Pick tariff** — select your tariff from the list. The tariff currently valid today is listed first.
3. **Options** — choose whether sensor values should include or exclude VAT (`inc_vat` / `ex_vat`). Optionally enter a Bearer token if your DSO requires authentication. Optionally select an **energy sensor** to enable running cost tracking (see [Running cost sensor](#running-cost-sensor) below).

## Sensors

Entity IDs are prefixed with the device name derived from your config entry (e.g. `sensor.goteborg_energi_nat_ab_sommartid_lag_active_power_band`). All entities for a given config entry are grouped under one device in the HA device registry.

### Tariff info sensors

| Entity | Unit | Description |
|--------|------|-------------|
| `…active_power_price` | SEK/kW | Price of the currently active power (effect) component |
| `…active_power_band` | — | Reference label of the active power band (e.g. `high`, `low`) |
| `…energy_price_total` | SEK/kWh | Sum of all active energy price components |
| `…energy_transfer_price` | SEK/kWh | The main energy transfer component (reference `main`) |
| `…energy_tax` | SEK/kWh | Energy tax component (reference `tax`) |
| `…fixed_price_annual` | SEK/year | Sum of all active fixed-price components |
| `…peaks_used_for_average` | peaks | Number of peak hours used in the effect tariff average |
| `…next_tariff_transition` | timestamp | Next datetime when the active tariff band changes |
| `…high_tariff_active` | — | `on` when a peak-priced power component is active |

Each sensor exposes only the state attributes relevant to it. The `today_schedule` attribute (hourly slots with `start`, `end`, `band`, and `price_inc_vat`) is available on `energy_price_total`, `energy_transfer_price`, and `next_tariff_transition`.

### Running cost sensor

When an energy sensor is configured, the integration adds one extra sensor:

| Entity | Unit | Description |
|--------|------|-------------|
| `…running_cost` | SEK | Total accumulated grid cost for the current billing period |

The sensor state is the sum of all cost components. The breakdown is available as attributes:

| Attribute | Description |
|-----------|-------------|
| `peak_cost` | Charged peak (kWh) × active power price (SEK/kW) |
| `transmission_cost` | Accumulated energy (kWh) × transfer rate |
| `tax_cost` | Accumulated energy (kWh) × tax rate |
| `fixed_cost` | Annual fixed cost prorated to elapsed billing period |
| `observed_peak_kwh` | Lowest stored peak — the floor you've committed to |
| `charged_peak_kwh` | Average of stored peaks — what you'll be billed for |
| `total_energy_kwh` | Total energy consumed this billing period |
| `stored_peaks` | List of stored peak records (`dt`, `kwh`) |
| `billing_period_start` | Start of the current billing period |
| `billing_period_end` | End of the current billing period |

Peak tracking uses the tariff's `peakIdentificationSettings` from the API:

- **`peakDuration`** (e.g. `PT1H`) — The window over which energy is measured to form a candidate peak.
- **`peakIdentificationPeriod`** (e.g. `P1D`) — Only the single highest peak per this period is kept.
- **`numberOfPeaksForAverageCalculation`** (e.g. `3`) — The top N peaks stored. The charged peak is their average.
- **`billingPeriod`** (e.g. `P1M`) — All peaks and accumulated costs reset at the start of each new billing period.

Peaks and accumulated costs **persist across HA restarts** via Home Assistant's restore-state mechanism — you won't lose your monthly data on a reboot.

## Preparing an energy sensor

The running cost sensor expects a **cumulative energy sensor in kWh**. If you only have a power sensor (watts), you can create one using Home Assistant's built-in helpers.

### Step 1 — Create a Riemann Sum integral sensor

Go to **Settings → Devices & Services → Helpers → Create Helper → Integration - Riemann sum integral** and configure:

| Setting | Value |
|---------|-------|
| Input sensor | Your power sensor (e.g. `sensor.house_power_w`) |
| Integration method | Left |
| Metric prefix | `k` (kilo) |
| Time unit | Hours |

This creates a cumulative kWh sensor (e.g. `sensor.house_power_w_integral`) that increases as energy is consumed.

> **Tip:** If your power sensor reports in watts (W), selecting prefix `k` and time unit `Hours` gives you kWh directly.

### Step 2 — (Optional) Create a Utility Meter for hourly resets

If your tariff uses `peakDuration: PT1H` (the most common setting), the integration already tracks hourly windows internally from the cumulative sensor. **You do not need a separate hourly utility meter** — just point the integration at the Riemann sum sensor from Step 1.

However, if you want a separate hourly energy sensor for your own dashboards:

Go to **Settings → Devices & Services → Helpers → Create Helper → Utility Meter** and configure:

| Setting | Value |
|---------|-------|
| Input sensor | The Riemann sum sensor from Step 1 |
| Cycle | Hourly |

### Step 3 — Select the energy sensor in the integration

Go to **Settings → Devices & Services → Eltariff → Configure** and select the Riemann sum sensor (or your native energy meter if you have one) in the **Energy sensor** field.

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

### React to your running grid cost

```yaml
automation:
  - alias: "Alert when grid cost exceeds 500 SEK"
    trigger:
      - platform: numeric_state
        entity_id: sensor.my_dso_my_tariff_running_cost
        above: 500
    action:
      - service: notify.mobile
        data:
          message: "Grid cost has passed 500 SEK this month."
```

## Known limitations

- **Catalogue API not implemented.** The RI-SE API spec includes an endpoint for looking up which DSO serves a given metering point (MPID). This integration does not use it — you must select your DSO manually.
- **`/prices` endpoint not consumed.** Some DSOs expose a `/prices` endpoint with time-varying energy prices. Most DSOs do not populate it yet, so this integration ignores it. Use Nordpool or Tibber for spot prices.
- **Running cost requires an energy sensor.** The integration does not integrate power readings itself. You need to provide a cumulative kWh sensor (see [Preparing an energy sensor](#preparing-an-energy-sensor)).
