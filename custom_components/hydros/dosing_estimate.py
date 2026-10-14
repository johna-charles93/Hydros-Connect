"""Estimated "dosed today" sensors for the HYDROS Public API path.

The Public API has no dosing-log endpoint, so the per-doser "Dosed Today"
sensors from the legacy path can't be built from real dose records. The API
does report each doser's reservoir level, though, so we estimate the daily
dose from how much the reservoir drops:

* a drop is counted as dosed volume;
* a rise is a refill and is ignored (the new level becomes the baseline);
* implausibly large drops (sensor glitch / reservoir swap) are ignored;
* the total resets at local midnight and the finished day goes into a short
  history, which drives an average and a "days remaining" estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN
from .entity_builders import build_output_display_name

_LOGGER = logging.getLogger(__name__)

SAMPLE_INTERVAL = timedelta(minutes=1)
# A single reading dropping more than this is treated as a glitch or a
# reservoir swap rather than a dose.
MAX_PLAUSIBLE_DROP_ML = 250.0
HISTORY_DAYS = 7


@dataclass
class DoseAccumulator:
    """Pure dose-from-reservoir bookkeeping (no Home Assistant dependencies)."""

    day: date
    today_ml: float = 0.0
    last_reading: float | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def roll_day(self, today: date) -> None:
        if today == self.day:
            return
        self.history.append({"date": self.day.isoformat(), "ml": round(self.today_ml, 1)})
        self.history = self.history[-HISTORY_DAYS:]
        self.today_ml = 0.0
        self.day = today

    def add_reading(self, reading: float, today: date) -> None:
        self.roll_day(today)
        if self.last_reading is None:
            self.last_reading = reading
            return
        delta = self.last_reading - reading
        if 0 < delta <= MAX_PLAUSIBLE_DROP_ML:
            self.today_ml += delta
        # Rises (refills) and glitches just reset the baseline.
        self.last_reading = reading

    @property
    def average_daily_ml(self) -> float | None:
        values = [float(d["ml"]) for d in self.history if float(d.get("ml", 0)) > 0]
        if not values:
            return None
        return round(sum(values) / len(values), 1)

    def days_remaining(self, reservoir_ml: float | None) -> float | None:
        avg = self.average_daily_ml
        if reservoir_ml is None or not avg:
            return None
        return round(reservoir_ml / avg, 1)


async def async_add_dosing_estimates(
    hass: HomeAssistant,
    hub: Any,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = []
    for thing_id in getattr(hub, "collective_ids", []):
        try:
            config = await hub.async_get_collective_config(thing_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Hydros dosing estimate: no config for %s: %s", thing_id, err)
            continue
        outputs = config.get("Output") if isinstance(config, dict) else None
        if not isinstance(outputs, dict):
            continue
        for output_key, output_meta in outputs.items():
            if not isinstance(output_meta, dict):
                continue
            if not hub.get_output_capabilities(thing_id, output_key).get("is_doser"):
                continue
            entities.append(
                HydrosDosedTodayEstimate(
                    entry=entry,
                    thing_id=thing_id,
                    output_key=output_key,
                    display_name=build_output_display_name(output_meta, output_key),
                )
            )
    if entities:
        async_add_entities(entities)


class HydrosDosedTodayEstimate(RestoreSensor):
    """Estimated volume dosed today, derived from the reservoir level."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfVolume.MILLILITERS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:beaker-outline"
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        thing_id: str,
        output_key: str,
        display_name: str,
    ) -> None:
        self._entry = entry
        self._thing_id = thing_id
        self._output_key = output_key
        self._attr_name = f"{display_name} dosed today (estimated)"
        self._attr_unique_id = (
            f"{entry.entry_id}-{thing_id}-{slugify(f'{thing_id}-dosed-estimate-{output_key}')}"
        )
        self._reservoir_unique_id = (
            f"{entry.entry_id}-{thing_id}-{slugify(f'{thing_id}-reservoir-{output_key}')}"
        )
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, thing_id)})
        self._acc = DoseAccumulator(day=dt_util.now().date())
        self._reservoir_ml: float | None = None
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        last_data = await self.async_get_last_sensor_data()
        if last_state is not None and last_data is not None:
            attrs = last_state.attributes
            try:
                saved_day = date.fromisoformat(str(attrs.get("day")))
            except ValueError:
                saved_day = self._acc.day
            history = attrs.get("daily_history")
            self._acc = DoseAccumulator(
                day=saved_day,
                today_ml=float(last_data.native_value or 0.0),
                last_reading=_as_float(attrs.get("last_reservoir_reading")),
                history=list(history) if isinstance(history, list) else [],
            )
            self._acc.roll_day(dt_util.now().date())

        self._unsub = async_track_time_interval(self.hass, self._async_sample, SAMPLE_INTERVAL)
        self._sample()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _async_sample(self, _now: Any) -> None:
        self._sample()

    @callback
    def _sample(self) -> None:
        reservoir_entity = er.async_get(self.hass).async_get_entity_id(
            "sensor", DOMAIN, self._reservoir_unique_id
        )
        reading = None
        if reservoir_entity:
            state = self.hass.states.get(reservoir_entity)
            reading = _as_float(state.state if state else None)
        today = dt_util.now().date()
        if reading is None:
            self._acc.roll_day(today)
        else:
            self._reservoir_ml = reading
            self._acc.add_reading(reading, today)
        self._attr_native_value = round(self._acc.today_ml, 1)
        self._attr_extra_state_attributes = {
            "estimated": True,
            "method": "reservoir level drop (refills ignored)",
            "reservoir_entity": reservoir_entity,
            "thing_id": self._thing_id,
            "output_key": self._output_key,
            "day": self._acc.day.isoformat(),
            "last_reservoir_reading": self._acc.last_reading,
            "daily_history": self._acc.history,
            "average_daily_ml": self._acc.average_daily_ml,
            "days_remaining": self._acc.days_remaining(self._reservoir_ml),
        }
        self.async_write_ha_state()


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
