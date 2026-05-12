"""Cost service — orchestrates energy tracking, peak tracking and cost accumulation.

The service is fed energy-sensor readings (cumulative kWh) and the current
tariff snapshot from the coordinator.  It maintains:

* Peak tracking via :class:`PeakTracker`.
* Incremental transmission and tax cost accumulation.
* A billing-period clock that resets everything on period boundaries.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .iso_duration import (
    ParsedDuration,
    elapsed_fraction,
    is_same_period,
    parse_iso_duration,
    period_end,
    period_start,
)
from .models import CostBreakdown, CostServiceState
from .peak_tracker import PeakTracker

if TYPE_CHECKING:
    from ..api.models.snapshot import ActiveTariffSnapshot

_LOGGER = logging.getLogger(__name__)

# Fallback durations when the API doesn't specify them.
_DEFAULT_BILLING_PERIOD = parse_iso_duration("P1M")
_DEFAULT_PEAK_DURATION = parse_iso_duration("PT1H")
_DEFAULT_IDENTIFICATION_PERIOD = parse_iso_duration("P1D")


class CostService:
    """Stateful cost accumulator for a single tariff entry.

    Instantiate once per config entry and call :meth:`on_energy_update` every
    time the energy sensor changes.  Call :meth:`get_breakdown` to read the
    current running cost.
    """

    def __init__(self) -> None:
        self._billing_duration: ParsedDuration = _DEFAULT_BILLING_PERIOD
        self._peak_duration: ParsedDuration = _DEFAULT_PEAK_DURATION
        self._id_period: ParsedDuration = _DEFAULT_IDENTIFICATION_PERIOD
        self._number_of_peaks: int = 1
        self._peak_function: str = "average"

        self._peak_tracker: PeakTracker | None = None

        # Billing period state
        self._billing_period_start: datetime | None = None
        self._deferred_peaks: list[dict] | None = None

        # Energy window state
        self._current_window_start: datetime | None = None
        self._current_window_start_reading: float | None = None
        self._current_window_peak: float = 0.0

        # Running totals
        self._prev_reading: float | None = None
        self._accumulated_transmission: float = 0.0
        self._accumulated_tax: float = 0.0
        self._total_energy_kwh: float = 0.0

        self._configured = False

    def configure_from_snapshot(self, snapshot: ActiveTariffSnapshot) -> None:
        """(Re-)configure durations and peak settings from the live snapshot.

        Called each coordinator cycle so the service always uses current data.
        Only rebuilds the PeakTracker on the first call or when settings change.
        """
        tariff = snapshot.tariff
        billing_str = tariff.billing_period or "P1M"

        pc = snapshot.active_power_component
        pis = pc.peak_identification_settings if pc else None

        id_period_str = (pis.peak_identification_period if pis else None) or "P1D"
        peak_dur_str = (pis.peak_duration if pis else None) or "PT1H"
        n_peaks = (pis.number_of_peaks_for_average if pis else None) or 1
        peak_fn = (pis.peak_function if pis else None) or "average"

        billing_dur = parse_iso_duration(billing_str)
        id_dur = parse_iso_duration(id_period_str)
        peak_dur = parse_iso_duration(peak_dur_str)

        needs_rebuild = (
            not self._configured
            or self._billing_duration != billing_dur
            or self._id_period != id_dur
            or self._peak_duration != peak_dur
            or self._number_of_peaks != n_peaks
            or self._peak_function != peak_fn
        )

        self._billing_duration = billing_dur
        self._id_period = id_dur
        self._peak_duration = peak_dur
        self._number_of_peaks = n_peaks
        self._peak_function = peak_fn

        if needs_rebuild:
            old_peaks = self._peak_tracker.serialise() if self._peak_tracker else []
            self._peak_tracker = PeakTracker(
                identification_period=self._id_period,
                number_of_peaks=self._number_of_peaks,
                peak_function=self._peak_function,
            )
            if old_peaks:
                self._peak_tracker.restore(old_peaks)
            elif self._deferred_peaks:
                self._peak_tracker.restore(self._deferred_peaks)
                self._deferred_peaks = None
            _LOGGER.debug(
                "CostService configured: billing=%s peak_dur=%s id_period=%s n=%d fn=%s",
                billing_str,
                peak_dur_str,
                id_period_str,
                n_peaks,
                peak_fn,
            )

        self._configured = True

    def on_energy_update(
        self,
        reading_kwh: float,
        now: datetime,
        snapshot: ActiveTariffSnapshot,
    ) -> None:
        """Process a new energy sensor reading.

        Parameters
        ----------
        reading_kwh:
            Cumulative energy reading from the HA sensor (kWh).
        now:
            Current datetime (timezone-aware).
        snapshot:
            The most recent tariff snapshot from the coordinator.
        """
        if not self._configured:
            self.configure_from_snapshot(snapshot)

        # --- Billing period transition ---
        if self._billing_period_start is not None and not is_same_period(
            now, self._billing_period_start, self._billing_duration
        ):
            _LOGGER.info("New billing period starting at %s", now.isoformat())
            self._reset_billing_period(now)

        if self._billing_period_start is None:
            self._billing_period_start = period_start(now, self._billing_duration)
            _LOGGER.debug("Billing period start set to %s", self._billing_period_start)

        # --- Accumulate energy costs ---
        if self._prev_reading is not None:
            delta = reading_kwh - self._prev_reading
            if delta < 0:
                # Sensor reset detected — treat as no delta this cycle.
                _LOGGER.debug(
                    "Energy sensor reset detected (%.3f → %.3f), skipping delta",
                    self._prev_reading,
                    reading_kwh,
                )
                delta = 0.0

            if delta > 0:
                self._total_energy_kwh += delta
                transmission_rate, tax_rate = self._energy_rates(snapshot)
                self._accumulated_transmission += delta * transmission_rate
                self._accumulated_tax += delta * tax_rate

        self._prev_reading = reading_kwh

        # --- Peak window tracking ---
        self._process_peak_window(reading_kwh, now)

    def get_breakdown(self, now: datetime, snapshot: ActiveTariffSnapshot) -> CostBreakdown:
        """Calculate and return the current cost breakdown."""
        if not self._configured:
            self.configure_from_snapshot(snapshot)

        peak_cost = self._compute_peak_cost(snapshot)
        fixed_cost = self._compute_fixed_cost(now, snapshot)
        currency = self._get_currency(snapshot)

        tracker = self._peak_tracker
        return CostBreakdown(
            peak_cost=peak_cost,
            transmission_cost=self._accumulated_transmission,
            tax_cost=self._accumulated_tax,
            fixed_cost=fixed_cost,
            observed_peak_kwh=tracker.observed_peak if tracker else 0.0,
            charged_peak_kwh=tracker.charged_peak if tracker else 0.0,
            stored_peaks=tracker.peaks if tracker else [],
            total_energy_kwh=self._total_energy_kwh,
            billing_period_start=self._billing_period_start,
            billing_period_end=(
                period_end(now, self._billing_duration)
                if self._billing_period_start
                else None
            ),
            currency=currency,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self) -> dict:
        """Return a serialisable dict for RestoreEntity."""
        return CostServiceState(
            billing_period_start_iso=(
                self._billing_period_start.isoformat()
                if self._billing_period_start
                else None
            ),
            peaks=self._peak_tracker.serialise() if self._peak_tracker else [],
            current_window_start_iso=(
                self._current_window_start.isoformat()
                if self._current_window_start
                else None
            ),
            current_window_start_reading=self._current_window_start_reading,
            current_window_peak=self._current_window_peak,
            prev_reading=self._prev_reading,
            accumulated_transmission_cost=self._accumulated_transmission,
            accumulated_tax_cost=self._accumulated_tax,
            total_energy_kwh=self._total_energy_kwh,
        ).to_dict()

    def restore_state(self, data: dict) -> None:
        """Restore from a previously saved dict."""
        state = CostServiceState.from_dict(data)

        if state.billing_period_start_iso:
            self._billing_period_start = datetime.fromisoformat(
                state.billing_period_start_iso
            )
        if state.current_window_start_iso:
            self._current_window_start = datetime.fromisoformat(
                state.current_window_start_iso
            )
        self._current_window_start_reading = state.current_window_start_reading
        self._current_window_peak = state.current_window_peak
        self._prev_reading = state.prev_reading
        self._accumulated_transmission = state.accumulated_transmission_cost
        self._accumulated_tax = state.accumulated_tax_cost
        self._total_energy_kwh = state.total_energy_kwh

        if self._peak_tracker and state.peaks:
            self._peak_tracker.restore(state.peaks)
        elif state.peaks:
            # PeakTracker not yet created; store for deferred restore.
            self._deferred_peaks = state.peaks

        _LOGGER.info("CostService state restored (peaks=%d)", len(state.peaks))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_billing_period(self, now: datetime) -> None:
        """Reset all accumulators for a new billing period."""
        self._billing_period_start = period_start(now, self._billing_duration)
        self._accumulated_transmission = 0.0
        self._accumulated_tax = 0.0
        self._total_energy_kwh = 0.0
        self._current_window_start = None
        self._current_window_start_reading = None
        self._current_window_peak = 0.0
        if self._peak_tracker:
            self._peak_tracker.reset()

    def _process_peak_window(self, reading_kwh: float, now: datetime) -> None:
        """Track the peak_duration window and record peaks."""
        if self._peak_tracker is None:
            return

        window_start_now = period_start(now, self._peak_duration)

        # Detect window transition
        if (
            self._current_window_start is not None
            and window_start_now != self._current_window_start
        ):
            # The previous window has ended — finalise its peak
            if self._current_window_peak > 0:
                self._peak_tracker.try_add_peak(
                    self._current_window_start, self._current_window_peak
                )

            # Reset for new window
            self._current_window_peak = 0.0
            self._current_window_start = window_start_now
            self._current_window_start_reading = self._prev_reading

        if self._current_window_start is None:
            self._current_window_start = window_start_now
            self._current_window_start_reading = reading_kwh

        # Update current window energy
        if self._current_window_start_reading is not None:
            window_energy = reading_kwh - self._current_window_start_reading
            if window_energy > self._current_window_peak:
                self._current_window_peak = window_energy
                # Also try to add/update peak in real-time
                self._peak_tracker.try_add_peak(
                    self._current_window_start, self._current_window_peak
                )

    def _energy_rates(
        self, snapshot: ActiveTariffSnapshot
    ) -> tuple[float, float]:
        """Extract current transmission and tax rates from the snapshot."""
        vat_mode = getattr(self, "_vat_mode", "inc_vat")
        transmission = 0.0
        tax = 0.0
        for comp in snapshot.active_energy_components:
            price = (
                comp.price.price_inc_vat
                if vat_mode == "inc_vat"
                else comp.price.price_ex_vat
            )
            if comp.reference == "tax":
                tax += price
            else:
                transmission += price
        return transmission, tax

    def _compute_peak_cost(self, snapshot: ActiveTariffSnapshot) -> float:
        """charged_peak × active power price."""
        if not self._peak_tracker:
            return 0.0
        charged = self._peak_tracker.charged_peak
        if charged <= 0:
            return 0.0

        pc = snapshot.active_power_component
        if pc is None:
            return 0.0

        vat_mode = getattr(self, "_vat_mode", "inc_vat")
        price = (
            pc.price.price_inc_vat if vat_mode == "inc_vat" else pc.price.price_ex_vat
        )
        return charged * price

    def _compute_fixed_cost(
        self, now: datetime, snapshot: ActiveTariffSnapshot
    ) -> float:
        """Prorate annual fixed costs to elapsed billing period."""
        if not snapshot.active_fixed_components:
            return 0.0

        vat_mode = getattr(self, "_vat_mode", "inc_vat")
        annual_total = sum(
            (
                c.price.price_inc_vat
                if vat_mode == "inc_vat"
                else c.price.price_ex_vat
            )
            for c in snapshot.active_fixed_components
        )

        if annual_total <= 0:
            return 0.0

        # Prorate: annual_total / 12 × fraction_elapsed_in_billing_period
        fraction = elapsed_fraction(now, self._billing_duration)
        # The fixed cost for one billing period
        period_fixed = annual_total / (12.0 if self._billing_duration.months == 1 else
                                       (365.25 / max(1, self._billing_duration.days))
                                       if self._billing_duration.days else 12.0)
        return period_fixed * fraction

    def _get_currency(self, snapshot: ActiveTariffSnapshot) -> str:
        """Best-effort currency from the snapshot."""
        for comp in snapshot.active_energy_components:
            return comp.price.currency
        pc = snapshot.active_power_component
        if pc:
            return pc.price.currency
        return "SEK"

    @property
    def vat_mode(self) -> str:
        return getattr(self, "_vat_mode", "inc_vat")

    @vat_mode.setter
    def vat_mode(self, value: str) -> None:
        self._vat_mode = value
