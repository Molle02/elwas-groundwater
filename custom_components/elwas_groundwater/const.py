"""Constants for the ELWAS Groundwater integration."""

from datetime import timedelta

DOMAIN = "elwas_groundwater"
NAME = "ELWAS Groundwater"
CONF_STATION_ID = "station_id"
DEFAULT_STATION_ID = "080200357"
DEFAULT_SCAN_INTERVAL = timedelta(hours=6)

ELWAS_URL = (
    "https://www.elwasweb.nrw.de/elwas-web/data/gw/zustand/gwm/"
    "grundwasserMst.xhtml?marea=1&mtheme=0&lindex=0&nested=true"
)

