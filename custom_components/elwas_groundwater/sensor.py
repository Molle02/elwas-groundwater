"""Sensor entities for ELWAS Groundwater."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import StationData
from .const import DOMAIN
from .coordinator import ElwasCoordinator


@dataclass(frozen=True, kw_only=True)
class ElwasSensorDescription(SensorEntityDescription):
    """Describe an ELWAS sensor."""

    value_fn: Callable[[StationData], float | int | str | date | None]


SENSORS = (
    ElwasSensorDescription(
        key="depth_to_groundwater",
        translation_key="depth_to_groundwater",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.latest.depth,
    ),
    ElwasSensorDescription(
        key="groundwater_level",
        translation_key="groundwater_level",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.latest.groundwater_level,
    ),
    ElwasSensorDescription(
        key="ground_level",
        translation_key="ground_level",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.latest.ground_level,
    ),
    ElwasSensorDescription(
        key="measurement_date",
        translation_key="measurement_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: data.latest.measured_on,
    ),
    ElwasSensorDescription(
        key="data_age",
        translation_key="data_age",
        native_unit_of_measurement="d",
        icon="mdi:calendar-clock",
        value_fn=lambda data: max((date.today() - data.latest.measured_on).days, 0),
    ),
    ElwasSensorDescription(
        key="trend_7d",
        translation_key="trend_7d",
        native_unit_of_measurement="cm/week",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-timeline-variant",
        suggested_display_precision=1,
        value_fn=lambda data: data.trend_7d_cm_week,
    ),
    ElwasSensorDescription(
        key="trend_30d",
        translation_key="trend_30d",
        native_unit_of_measurement="cm/week",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-timeline-variant",
        suggested_display_precision=1,
        value_fn=lambda data: data.trend_30d_cm_week,
    ),
    ElwasSensorDescription(
        key="trend_direction",
        translation_key="trend_direction",
        device_class=SensorDeviceClass.ENUM,
        options=["rising", "stable", "falling"],
        icon="mdi:swap-vertical-bold",
        value_fn=lambda data: data.trend_direction,
    ),
    ElwasSensorDescription(
        key="seasonal_mean_depth",
        translation_key="seasonal_mean_depth",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.seasonal_mean_depth,
    ),
    ElwasSensorDescription(
        key="seasonal_anomaly",
        translation_key="seasonal_anomaly",
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:delta",
        suggested_display_precision=2,
        value_fn=lambda data: data.seasonal_anomaly_depth,
    ),
    ElwasSensorDescription(
        key="seasonal_percentile",
        translation_key="seasonal_percentile",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent-outline",
        suggested_display_precision=0,
        value_fn=lambda data: data.seasonal_percentile,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all ELWAS sensors."""
    coordinator: ElwasCoordinator = entry.runtime_data
    async_add_entities(ElwasSensor(coordinator, entry, description) for description in SENSORS)


class ElwasSensor(CoordinatorEntity[ElwasCoordinator], SensorEntity):
    """A sensor based on the shared station export."""

    entity_description: ElwasSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ElwasCoordinator,
        entry: ConfigEntry,
        description: ElwasSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.station_id)},
            name=entry.title,
            manufacturer="Land NRW / LANUK",
            model="ELWAS groundwater station",
            configuration_url="https://www.elwasweb.nrw.de/elwas-web/index.xhtml",
        )

    @property
    def native_value(self) -> float | int | str | date | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, str | int | float | None]:
        """Expose the station reference and calculation context."""
        data = self.coordinator.data
        return {
            "station_id": data.station_id,
            "station_name": data.station_name,
            "series_start": data.series_start.isoformat(),
            "series_end": data.series_end.isoformat(),
            "measurement_count": data.measurement_count,
            "long_term_mean_depth": data.long_term_mean_depth,
            "long_term_mean_level": data.long_term_mean_level,
            "seasonal_reference_window_days": 15,
            "trend_sign_note": "negative=rising groundwater, positive=falling groundwater",
            "height_reference": "NHN2016",
        }
