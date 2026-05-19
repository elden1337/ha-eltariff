# HA Eltariff

[![Total_downloads](https://img.shields.io/github/downloads/elden1337/ha-eltariff/total)](https://github.com/elden1337/ha-eltariff)
[![Latst version_downloads](https://img.shields.io/github/downloads/elden1337/ha-eltariff/latest/total)](https://github.com/elden1337/ha-eltariff)

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

The setup flow has three required steps, plus one optional step if you want running cost and peak tracking:

1. **Pick DSO** — select your grid owner from the dropdown. The integration validates the endpoint before proceeding.
2. **Pick tariff** — select your tariff from the list. The tariff currently valid today is listed first.
3. **Options** — choose whether sensor values should include or exclude VAT (`inc_vat` / `ex_vat`). Optionally enter a Bearer token if your DSO requires authentication.
4. **(Optional) Running cost setup** — select an **energy sensor** to enable `running_cost`, `observed_peak`, and `charged_peak` sensors (see [Optional step 4 — enable running cost tracking](#optional-step-4--enable-running-cost-tracking)).

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
| `…price_curve` | SEK/kWh | Current-hour price from a dynamic price-curve component (see [Price curves](#price-curves)) |

Each sensor exposes only the state attributes relevant to it. The `today_schedule` attribute (hourly slots with `start`, `end`, `band`, and `price_inc_vat`) is available on `energy_price_total`, `energy_transfer_price`, and `next_tariff_transition`.

### Running cost sensor

When an energy sensor is configured, the integration adds cost-tracking sensors:

| Entity | Unit | Description |
|--------|------|-------------|
| `…running_cost` | SEK | Total accumulated grid cost for the current billing period |
| `…transmission_cost` | SEK | Running transmission (energy transfer) cost |
| `…tax_cost` | SEK | Running energy tax cost |
| `…price_curve_cost` | SEK | Running price-curve cost (only if dynamic price-curve components exist) |
| `…peak_cost` | SEK | Peak power cost (only if tariff has a power component) |
| `…observed_peak` | kW | Highest peak power recorded this billing period |
| `…charged_peak` | kW | Peak power you will be billed for (only if tariff has a power component) |

The sensor state is the sum of all cost components. The breakdown is available as attributes:

| Attribute | Description |
|-----------|-------------|
| `peak_cost` | Charged peak (kWh) × active power price (SEK/kW) |
| `transmission_cost` | Accumulated energy (kWh) × transfer rate |
| `tax_cost` | Accumulated energy (kWh) × tax rate |
| `price_curve_cost` | Accumulated energy (kWh) × dynamic price-curve rate |
| `fixed_cost` | Annual fixed cost prorated to elapsed billing period |
| `total_energy_kwh` | Total energy consumed this billing period |
| `billing_period_start` | Start of the current billing period |
| `billing_period_end` | End of the current billing period |

Peak tracking uses the tariff's `peakIdentificationSettings` from the API:

- **`peakDuration`** (e.g. `PT1H`) — The window over which energy is measured to form a candidate peak.
- **`peakIdentificationPeriod`** (e.g. `P1D`) — Only the single highest peak per this period is kept.
- **`numberOfPeaksForAverageCalculation`** (e.g. `3`) — The top N peaks stored. The charged peak is their average.
- **`billingPeriod`** (e.g. `P1M`) — All peaks and accumulated costs reset at the start of each new billing period.

> **Note:** If your tariff has no power (effect) component — common with price-curve-only tariffs — the integration still tracks the **observed peak** for reference (useful when the contract has an absolute power ceiling), but will not create the `charged_peak` or `peak_cost` sensors since there is no peak billing.

Peaks and accumulated costs **persist across HA restarts** via Home Assistant's restore-state mechanism — you won't lose your monthly data on a reboot.

## Price curves

Some DSOs define dynamic grid tariff components whose price varies hourly — published via the API's `/prices` endpoint. These are **not** electricity spot prices; they are grid tariff curves set by the DSO.

When a tariff contains a component with a `url` field (pointing to `/prices/{componentId}`), the integration automatically:

1. **Fetches today's prices** on the first coordinator cycle.
2. **Polls for tomorrow's prices** starting at noon (local time) every ~5 minutes, with per-instance jitter to avoid thundering herd.
3. **Overlays** the hourly price into the tariff snapshot so existing sensors (`energy_price_total`, `energy_transfer_price`) reflect the live rate.

### Price curve sensor

For each dynamic component the integration creates a `…price_curve` sensor:

| Attribute | Description |
|-----------|-------------|
| `today` | List of hourly entries for today (`start`, `end`, `price_ex_vat`, `price_inc_vat`) |
| `tomorrow` | List of hourly entries for tomorrow (empty until published) |
| `component_id` | UUID of the underlying price component |

The sensor state is the price for the current hour.

### Price curve running cost

When an energy sensor is configured and price-curve components exist, a `…price_curve_cost` sensor tracks the accumulated cost from those components separately from the static transmission fee.  This cost is also included in the `…running_cost` total and its `price_curve_cost` attribute.

### Coexistence with static tariffs

A tariff can have both static energy components (fixed transfer fee) and dynamic price-curve components. The integration handles both: static components accumulate into `transmission_cost`, dynamic components into `price_curve_cost`, and both contribute to `running_cost`.

## Optional step 4 — enable running cost tracking

If you only want tariff info sensors, you can skip this section.  
If you also want `running_cost`, `observed_peak`, and `charged_peak`, complete this optional step.

### Preparing an energy sensor

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

### React to your current peak level (observed peak)

```yaml
automation:
  - alias: "Warn when observed peak gets high"
    trigger:
      - platform: numeric_state
        entity_id: sensor.my_dso_my_tariff_observed_peak
        above: 8
    action:
      - service: notify.mobile
        data:
          message: "Observed peak is now above 8 kW. Avoid starting more high-load devices."
```

## Known limitations

- **Catalogue API not implemented.** The RI-SE API spec includes an endpoint for looking up which DSO serves a given metering point (MPID). This integration does not use it — you must select your DSO manually.
- **Price curves not yet live.** The `/prices` endpoint is implemented and tested, but no DSO currently populates it. The integration is ready to consume it once a DSO starts publishing dynamic price curves.
- **Running cost requires an energy sensor.** The integration does not integrate power readings itself. You need to provide a cumulative kWh sensor (see [Preparing an energy sensor](#preparing-an-energy-sensor)).
