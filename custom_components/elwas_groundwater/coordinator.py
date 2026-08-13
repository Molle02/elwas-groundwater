"""Coordinator for ELWAS Groundwater."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ElwasError, ElwasGroundwaterClient, StationData
from .const import CONF_STATION_ID, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ElwasCoordinator(DataUpdateCoordinator[StationData]):
    """Update one ELWAS station for all entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ElwasGroundwaterClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self.station_id = entry.data[CONF_STATION_ID]

    async def _async_update_data(self) -> StationData:
        try:
            return await self.client.async_get_station_data(self.station_id)
        except ElwasError as err:
            raise UpdateFailed(str(err)) from err

