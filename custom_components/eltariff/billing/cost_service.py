"""Cost service — orchestrates energy tracking, peak tracking and cost accumulation.

The service is fed energy-sensor readings (cumulative kWh) and the current
tariff snapshot from the coordinator.  It maintains:

* Peak tracking via :class:`PeakTracker` (one per power component).
* Incremental transmission and tax cost accumulation.
* A billing-period clock that resets everything on period boundaries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .iso_duration import (
    ParsedDuration,
    is_same_period,
    parse_iso_duration,
    period_end,
    period_start,
)
from .models import CostBreakdown, CostServiceState, PeakRecord
from .peak_tracker import PeakTracker

if TYPE_CHECKING:
    from ..api.models.snapshot import ActiveTariffSnapshot

_LOGGER = logging.getLogger(__name__)

# Fallback durations when the API doesn't specify them.
_DEFAULT_BILLING_PERIOD = parse_iso_duration("P1M")
_DEFAULT_PEAK_DURATION = parse_iso_duration("PT1H")
_DEFAULT_IDENTIFICATION_PERIOD = parse_iso_duration("P1D")

# Key used when the active power component has no string id (e.g. in older
# tests that use plain MagicMock without setting pc.id).
_GLOBAL_KEY = "__global__"


class CostService:
    """Stateful cost accumulator for a single tariff entry.

    Instantiate once per config entry and call :meth:`on_energy_update` every
    time the energy sensor changes.  Call :meth:`get_breakdown` to read the
    current running cost.
    """

    def __init__(self) -> None:
        self._vat_mode: str = "inc_vat"
        self._billing_duration: ParsedDuration = _DEFAULT_BILLING_PERIOD
        self._peak_duration: ParsedDuration = _DEFAULT_PEAK_DURATION
        self._id_period: ParsedDuration = _DEFAULT_IDENTIFICATION_PERIOD
        self._number_of_peaks: int = 1
        self._peak_function: str = "average"

        # One PeakTracker per power-component id.  Keyed by _component_key().
        self._peak_trackers: dict[str, PeakTracker] = {}

        # Billing period state
        self._billing_period_start: datetime | None = None
        self._deferred_peaks: list[PeakRecord] | None = None

        # Energy window state
        self._current_window_start: datetime | None = None
        self._current_window_start_reading: float | None = None
        self._current_window_peak: float = 0.0
        self._current_window_component_id: str | None = None

        # Running totals
        self._prev_reading: float | None = None
        self._accumulated_transmission: float = 0.0
        self._accumulated_tax: float = 0.0
        self._total_energy_kwh: float = 0.0

        self._configured = False
        self._state_restored = False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure_from_snapshot(self, snapshot: ActiveTariffSnapshot) -> None:
        """(Re-)configure durations and peak settings from the live snapshot.

        Called each coordinator cycle so the service always uses current data.
        Only rebuilds the PeakTrackers on the first call or when settings change.
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
            # Rebuild every existing per-component tracker with new settings,
            # preserving the peaks they hold.
            new_trackers: dict[str, PeakTracker] = {}
            for cid, old_tracker in self._peak_trackers.items():
                new_tracker = PeakTracker(
                    identification_period=self._id_period,
                    number_of_peaks=self._number_of_peaks,
                    peak_function=self._peak_function,
                )
                old_peaks = old_tracker.serialise()
                if old_peaks:
                    new_tracker.restore(old_peaks)
                new_trackers[cid] = new_tracker
            self._peak_trackers = new_trackers

            if not self._peak_trackers and self._deferred_peaks:
                # Restore deferred peaks grouped by component_id.
                by_comp: dict[str, list[PeakRecord]] = {}
                for record in self._deferred_peaks:
                    key = record.component_id or _GLOBAL_KEY
                    by_comp.setdefault(key, []).append(record)
                for cid, records in by_comp.items():
                    tracker = self._get_or_create_tracker(cid)
                    tracker.restore(records)
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

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_energy_update(
        self,
        reading_kwh: float,
        now: datetime,
        snapshot: ActiveTariffSnapshot,
    ) -> None:
        """Process a new energy sensor reading."""
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
        self._process_peak_window(reading_kwh, now, snapshot)

    def get_breakdown(self, now: datetime, snapshot: ActiveTariffSnapshot) -> CostBreakdown:
        """Calculate and return the current cost breakdown."""
        if not self._configured:
            self.configure_from_snapshot(snapshot)

        peak_cost = self._compute_peak_cost(snapshot)
        fixed_cost = self._compute_fixed_cost(snapshot)
        currency = self._get_currency(snapshot)

        key = self._component_key(snapshot)
        tracker = self._peak_trackers.get(key)
        return CostBreakdown(
            peak_cost=peak_cost,
            transmission_cost=self._accumulated_transmission,
            tax_cost=self._accumulated_tax,
            fixed_cost=fixed_cost,
            observed_peak_kwh=tracker.observed_peak if tracker else 0.0,
            charged_peak_kwh=tracker.charged_peak if tracker else 0.0,
            peak_duration_hours=self._peak_duration_hours(),
            stored_peaks=tracker.peaks if tracker else [],
            total_energy_kwh=self._total_energy_kwh,
            billing_period_start=self._billing_period_start,
            billing_period_end=(
                period_end(now, self._billing_duration) if self._billing_period_start else None
            ),
            currency=currency,
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self) -> dict:
        """Return a serialisable dict for RestoreEntity."""
        # Flatten all per-component peaks into a single list, tagging each
        # record with its component_id so restore_state can re-group them.
        all_peaks: list[PeakRecord] = []
        for cid, tracker in self._peak_trackers.items():
            for record in tracker.serialise():
                all_peaks.append(PeakRecord(dt=record.dt, value=record.value, component_id=cid))

        return CostServiceState(
            billing_period_start_iso=(
                self._billing_period_start.isoformat() if self._billing_period_start else None
            ),
            peaks=all_peaks,
            current_window_start_iso=(
                self._current_window_start.isoformat() if self._current_window_start else None
            ),
            current_window_start_reading=self._current_window_start_reading,
            current_window_peak=self._current_window_peak,
            prev_reading=self._prev_reading,
            accumulated_transmission_cost=self._accumulated_transmission,
            accumulated_tax_cost=self._accumulated_tax,
            total_energy_kwh=self._total_energy_kwh,
        ).to_dict()

    def restore_state(self, data: dict) -> None:
        """Restore from a previously saved dict.

        Only the first call takes effect; subsequent calls are ignored so that
        multiple sensors sharing the same CostService don't overwrite each other.
        """
        if self._state_restored:
            return

        state = CostServiceState.from_dict(data)

        if state.billing_period_start_iso:
            self._billing_period_start = datetime.fromisoformat(state.billing_period_start_iso)
        if state.current_window_start_iso:
            self._current_window_start = datetime.fromisoformat(state.current_window_start_iso)
        self._current_window_start_reading = state.current_window_start_reading
        self._current_window_peak = state.current_window_peak
        self._prev_reading = state.prev_reading
        self._accumulated_transmission = state.accumulated_transmission_cost
        self._accumulated_tax = state.accumulated_tax_cost
        self._total_energy_kwh = state.total_energy_kwh

        if state.peaks:
            if self._peak_trackers:
                # Trackers already exist — re-group and restore into them.
                by_comp: dict[str, list[PeakRecord]] = {}
                for record in state.peaks:
                    key = record.component_id or _GLOBAL_KEY
                    by_comp.setdefault(key, []).append(record)
                for cid, records in by_comp.items():
                    tracker = self._get_or_create_tracker(cid)
                    tracker.restore(records)
            else:
                # PeakTrackers not yet created; store for deferred restore.
                self._deferred_peaks = list(state.peaks)

        _LOGGER.info("CostService state restored (peaks=%d)", len(state.peaks))
        self._state_restored = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _component_key(self, snapshot: ActiveTariffSnapshot) -> str:
        """Return a stable string key for the active power component.

        Falls back to _GLOBAL_KEY when the component has no string id (e.g.
        plain MagicMock in tests that don't set pc.id explicitly).
        """
        pc = snapshot.active_power_component
        if pc is None:
            return "__none__"
        cid = getattr(pc, "id", None)
        return cid if isinstance(cid, str) else _GLOBAL_KEY

    def _get_or_create_tracker(self, key: str) -> PeakTracker:
        if key not in self._peak_trackers:
            self._peak_trackers[key] = PeakTracker(
                identification_period=self._id_period,
                number_of_peaks=self._number_of_peaks,
                peak_function=self._peak_function,
            )
        return self._peak_trackers[key]

    def _reset_billing_period(self, now: datetime) -> None:
        """Reset all accumulators for a new billing period."""
        self._billing_period_start = period_start(now, self._billing_duration)
        self._accumulated_transmission = 0.0
        self._accumulated_tax = 0.0
        self._total_energy_kwh = 0.0
        self._current_window_start = None
        self._current_window_start_reading = None
        self._current_window_peak = 0.0
        self._current_window_component_id = None
        for tracker in self._peak_trackers.values():
            tracker.reset()

    def _process_peak_window(
        self, reading_kwh: float, now: datetime, snapshot: ActiveTariffSnapshot
    ) -> None:
        """Track the peak_duration window and record peaks per component."""
        comp_key = self._component_key(snapshot)
        window_start_now = period_start(now, self._peak_duration)

        # Detect window transition
        if (
            self._current_window_start is not None
            and window_start_now != self._current_window_start
        ):
            # Finalise the previous window under whichever component was active then.
            if self._current_window_peak > 0 and self._current_window_component_id is not None:
                tracker = self._get_or_create_tracker(self._current_window_component_id)
                tracker.try_add_peak(self._current_window_start, self._current_window_peak)

            # Reset for new window
            self._current_window_peak = 0.0
            self._current_window_start = window_start_now
            self._current_window_start_reading = self._prev_reading
            self._current_window_component_id = comp_key

        if self._current_window_start is None:
            self._current_window_start = window_start_now
            self._current_window_start_reading = reading_kwh
            self._current_window_component_id = comp_key

        # Update current window energy
        if self._current_window_start_reading is not None:
            window_energy = reading_kwh - self._current_window_start_reading
            if window_energy > self._current_window_peak:
                self._current_window_peak = window_energy
                # Real-time update to the tracker that owns this window.
                if self._current_window_component_id is not None:
                    tracker = self._get_or_create_tracker(self._current_window_component_id)
                    tracker.try_add_peak(self._current_window_start, self._current_window_peak)

    def _energy_rates(self, snapshot: ActiveTariffSnapshot) -> tuple[float, float]:
        """Extract current transmission and tax rates from the snapshot."""
        vat_mode = self._vat_mode
        transmission = 0.0
        tax = 0.0
        for comp in snapshot.active_energy_components:
            price = comp.price.price_inc_vat if vat_mode == "inc_vat" else comp.price.price_ex_vat
            if comp.reference == "tax":
                tax += price
            else:
                transmission += price
        return transmission, tax

    def _compute_peak_cost(self, snapshot: ActiveTariffSnapshot) -> float:
        """charged_peak for the active component × its price."""
        pc = snapshot.active_power_component
        if pc is None:
            return 0.0
        key = self._component_key(snapshot)
        tracker = self._peak_trackers.get(key)
        if not tracker:
            return 0.0
        charged = tracker.charged_peak
        if charged <= 0:
            return 0.0
        vat_mode = self._vat_mode
        price = pc.price.price_inc_vat if vat_mode == "inc_vat" else pc.price.price_ex_vat
        return charged * price

    def _compute_fixed_cost(self, snapshot: ActiveTariffSnapshot) -> float:
        """Return the full fixed cost for the current billing period (lump sum)."""
        if not snapshot.active_fixed_components:
            return 0.0

        vat_mode = self._vat_mode
        annual_total = sum(
            (c.price.price_inc_vat if vat_mode == "inc_vat" else c.price.price_ex_vat)
            for c in snapshot.active_fixed_components
        )

        if annual_total <= 0:
            return 0.0

        dur = self._billing_duration
        if dur.years:
            divisor = 1.0
        elif dur.months:
            divisor = 12.0 / dur.months
        elif dur.days:
            divisor = 365.25 / dur.days
        else:
            divisor = 12.0
        return annual_total / divisor

    def _peak_duration_hours(self) -> float:
        d = self._peak_duration
        hours = d.years * 8766.0 + d.months * 730.5 + d.days * 24.0 + d.hours + d.minutes / 60.0
        return max(hours, 1.0 / 60.0)

    def _get_currency(self, snapshot: ActiveTariffSnapshot) -> str:
        """Best-effort currency from the snapshot."""
        for comp in snapshot.active_energy_components:
            return comp.price.currency
        pc = snapshot.active_power_component
        if pc:
            return pc.price.currency
        return "SEK"

    @property
    def _peak_tracker(self) -> PeakTracker | None:
        """Backward-compatible accessor used by tests that pre-date per-component tracking."""
        if not self._configured:
            return None
        return self._get_or_create_tracker(_GLOBAL_KEY)

    @property
    def vat_mode(self) -> str:
        return self._vat_mode

    @vat_mode.setter
    def vat_mode(self, value: str) -> None:
        self._vat_mode = value
