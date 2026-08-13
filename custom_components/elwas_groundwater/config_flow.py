"""Config flow for ELWAS Groundwater."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import ElwasConnectionError, ElwasError, ElwasGroundwaterClient, StationNotFoundError
from .const import CONF_STATION_ID, DEFAULT_STATION_ID, DOMAIN


class ElwasGroundwaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure an ELWAS groundwater station."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Validate an LGD station and create its entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = str(user_input[CONF_STATION_ID]).strip()
            if not station_id.isdigit() or len(station_id) != 9:
                errors["base"] = "invalid_station_id"
            else:
                client = ElwasGroundwaterClient(async_get_clientsession(self.hass))
                try:
                    data = await client.async_get_station_data(station_id)
                except StationNotFoundError:
                    errors["base"] = "station_not_found"
                except ElwasConnectionError:
                    errors["base"] = "cannot_connect"
                except ElwasError:
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(station_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"{data.station_name} ({station_id})",
                        data={CONF_STATION_ID: station_id},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_STATION_ID, default=DEFAULT_STATION_ID): str}
            ),
            errors=errors,
        )

