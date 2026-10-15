"""Binary sensors for ELWAS Groundwater."""

from __future__ import annotations

from datetime import date

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ElwasCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the stale-data warning."""
    coordinator: ElwasCoordinator = entry.runtime_data
    async_add_entities([ElwasDataStaleSensor(coordinator, entry)])


class ElwasDataStaleSensor(CoordinatorEntity[ElwasCoordinator], BinarySensorEntity):
    """Warn when the newest published measurement is older than seven days."""

    _attr_has_entity_name = True
    _attr_translation_key = "data_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ElwasCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_data_stale"
        self._attr_device_info = {
            "identifiers": {("elwas_groundwater", coordinator.station_id)}
        }

    @property
    def is_on(self) -> bool:
        """Return true when ELWAS data is more than seven days old."""
        return (date.today() - self.coordinator.data.latest.measured_on).days > 7

