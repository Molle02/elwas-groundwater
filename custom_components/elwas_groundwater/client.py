"""Asynchronous client for station-specific ELWAS groundwater exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
import io
import math
import statistics
from typing import Final
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
import zipfile

from aiohttp import ClientError, ClientSession

from .const import ELWAS_URL

_XLSX_NS: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS = {"x": _XLSX_NS}


class ElwasError(Exception):
    """Base error raised by the ELWAS client."""


class ElwasConnectionError(ElwasError):
    """ELWAS could not be reached."""


class StationNotFoundError(ElwasError):
    """The requested LGD station was not found or is not public."""


class ElwasFormatError(ElwasError):
    """ELWAS returned an unexpected page or workbook."""


@dataclass(frozen=True, slots=True)
class Measurement:
    """One groundwater measurement."""

    measured_on: date
    depth: float
    groundwater_level: float
    ground_level: float
    measuring_point_level: float | None = None
    drawdown: float | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class StationData:
    """Current ELWAS values and derived statistics."""

    station_id: str
    station_name: str
    latest: Measurement
    measurement_count: int
    series_start: date
    series_end: date
    trend_7d_cm_week: float | None
    trend_30d_cm_week: float | None
    trend_direction: str
    seasonal_mean_depth: float | None
    seasonal_anomaly_depth: float | None
    seasonal_percentile: float | None
    long_term_mean_depth: float
    long_term_mean_level: float


@dataclass(slots=True)
class _Form:
    action: str = ""
    fields: list[tuple[str, str]] = field(default_factory=list)
    controls: list[tuple[str, str, str]] = field(default_factory=list)

    def has_name_ending(self, suffix: str) -> bool:
        return any(name.endswith(suffix) for name, _ in self.fields) or any(
            name.endswith(suffix) for name, _, _ in self.controls
        )


class _FormsParser(HTMLParser):
    """Collect successful fields and submit controls from JSF forms."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_Form] = []
        self._form: _Form | None = None
        self._select_name: str | None = None
        self._select_options: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        if tag == "form":
            self._form = _Form(action=attrs.get("action", ""))
            self.forms.append(self._form)
            return
        if self._form is None:
            return
        if tag == "input":
            name = attrs.get("name", "")
            input_type = attrs.get("type", "text").lower()
            value = attrs.get("value", "")
            if not name or "disabled" in attrs:
                return
            if input_type in {"submit", "button", "image"}:
                self._form.controls.append((name, value, attrs.get("id", "")))
            elif input_type not in {"reset", "file"} and (
                input_type not in {"checkbox", "radio"} or "checked" in attrs
            ):
                self._form.fields.append((name, value))
            return
        if tag == "button":
            name = attrs.get("name", "")
            if name:
                self._form.controls.append((name, attrs.get("value", ""), attrs.get("id", "")))
            return
        if tag == "select":
            self._select_name = attrs.get("name", "")
            self._select_options = []
            return
        if tag == "option" and self._select_name:
            self._select_options.append((attrs.get("value", ""), "selected" in attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._form is not None and self._select_name:
            selected = next((value for value, is_selected in self._select_options if is_selected), None)
            if selected is None and self._select_options:
                selected = self._select_options[0][0]
            if selected is not None:
                self._form.fields.append((self._select_name, selected))
            self._select_name = None
            self._select_options = []
        elif tag == "form":
            self._form = None


class _WaterTableParser(HTMLParser):
    """Read the station title and water-level rows from the ELWAS detail page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.station_name = ""
        self.rows: list[list[str]] = []
        self._in_title = False
        self._in_table = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value or "" for key, value in attrs_list}
        element_id = attrs.get("id", "")
        if tag == "span" and element_id == "itemTitle":
            self._in_title = True
        elif tag == "tbody" and "p-tablewasserUndFlurAbstaendeErg_data" in element_id:
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.station_name += data
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._in_title:
            self._in_title = False
        elif tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag == "tbody" and self._in_table:
            self._in_table = False


class ElwasGroundwaterClient:
    """Download and analyze one public ELWAS station export."""

    def __init__(
        self,
        session: ClientSession,
        *,
        base_url: str = ELWAS_URL,
        timeout: int = 60,
    ) -> None:
        self._session = session
        self._base_url = base_url
        self._timeout = timeout

    async def async_get_station_data(self, station_id: str) -> StationData:
        """Fetch the station workbook and return current and historic statistics."""
        normalized = station_id.strip()
        if not normalized.isdigit() or len(normalized) != 9:
            raise ValueError("An LGD station ID must contain exactly nine digits")
        station_name, measurements = await self._async_fetch_measurements(normalized)
        return calculate_statistics(normalized, station_name, measurements)

    async def _async_fetch_measurements(
        self, station_id: str
    ) -> tuple[str, list[Measurement]]:
        html, page_url = await self._get_html(self._base_url)

        search_form = _find_form(html, ":mstnrId")
        station_field = _find_field_name(search_form, ":mstnrId")
        search_control = _find_control(search_form, "gwMs_search")
        search_data = _replace_field(search_form.fields, station_field, station_id)
        search_data.append((search_control[0], search_control[1] or "Suchen"))
        html, page_url = await self._post_html(page_url, search_form.action, search_data)
        if station_id not in html:
            raise StationNotFoundError(f"ELWAS station {station_id} was not found")

        result_form = _find_form_with_control_value(html, station_id)
        station_control = next(control for control in result_form.controls if control[1] == station_id)
        detail_data = list(result_form.fields)
        detail_data.append((station_control[0], station_control[1]))
        html, page_url = await self._post_html(page_url, result_form.action, detail_data)

        detail_form = _find_form(html, ":dDSwitcher")
        switch_name = _find_field_name(detail_form, ":dDSwitcher")
        form_id = _find_jsf_form_id(detail_form)
        faces_namespace = _find_faces_namespace(detail_form)
        switch_data = _replace_field(detail_form.fields, switch_name, "5")
        switch_data.extend(
            [
                (f"{faces_namespace}.partial.ajax", "true"),
                (f"{faces_namespace}.source", switch_name),
                # Mojarra expands @form in the browser before sending the
                # request.  Sending the literal token makes ELWAS keep the
                # "Stammdaten" view and therefore hides the Excel export.
                (f"{faces_namespace}.partial.execute", f"{switch_name} {form_id}"),
                (f"{faces_namespace}.partial.render", "@all"),
                (f"{faces_namespace}.behavior.event", "change"),
                (f"{faces_namespace}.partial.event", "change"),
            ]
        )
        partial, page_url = await self._post_text(
            page_url,
            detail_form.action,
            switch_data,
            headers={"Faces-Request": "partial/ajax"},
        )
        html = _extract_jsf_update(partial)
        return parse_station_html(html, station_id)

    async def _get_html(self, url: str) -> tuple[str, str]:
        try:
            async with self._session.get(url, timeout=self._timeout) as response:
                response.raise_for_status()
                return await response.text(), str(response.url)
        except (ClientError, TimeoutError) as err:
            raise ElwasConnectionError(str(err)) from err

    async def _post_text(
        self,
        current_url: str,
        action: str,
        data: list[tuple[str, str]],
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        url = urljoin(current_url, action)
        try:
            async with self._session.post(
                url, data=data, headers=headers, timeout=self._timeout
            ) as response:
                response.raise_for_status()
                return await response.text(), str(response.url)
        except (ClientError, TimeoutError) as err:
            raise ElwasConnectionError(str(err)) from err

    async def _post_html(
        self, current_url: str, action: str, data: list[tuple[str, str]]
    ) -> tuple[str, str]:
        return await self._post_text(current_url, action, data)

def parse_station_html(html: str, station_id: str) -> tuple[str, list[Measurement]]:
    """Parse the complete water-level table embedded in the ELWAS detail view."""
    parser = _WaterTableParser()
    parser.feed(html)
    measurements: list[Measurement] = []
    for row in parser.rows:
        if len(row) < 7:
            continue
        try:
            measurements.append(
                Measurement(
                    measured_on=date.fromisoformat(row[0]),
                    drawdown=_optional_number(row[1]),
                    note=row[2],
                    groundwater_level=_number(row[3]),
                    depth=_number(row[4]),
                    ground_level=_number(row[5]),
                    measuring_point_level=_optional_number(row[6]),
                )
            )
        except ValueError:
            # ELWAS also publishes rows labelled "nicht gemessen".
            continue
    if not measurements:
        raise ElwasFormatError(f"ELWAS detail page contains no values for {station_id}")
    title = " ".join(parser.station_name.split())
    station_name = title.split("(", 1)[0].strip() or station_id
    return station_name, sorted(measurements, key=lambda item: item.measured_on)


def parse_station_workbook(payload: bytes, station_id: str) -> tuple[str, list[Measurement]]:
    """Parse an ELWAS XLSX without third-party spreadsheet dependencies."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as workbook:
            shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            sheet_root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as err:
        raise ElwasFormatError("Invalid ELWAS XLSX workbook") from err

    shared = ["".join(node.itertext()) for node in shared_root.findall("x:si", _NS)]
    rows: list[list[str]] = []
    for row_node in sheet_root.findall(".//x:sheetData/x:row", _NS):
        values: dict[int, str] = {}
        for cell in row_node.findall("x:c", _NS):
            reference = cell.get("r", "A1")
            column = _column_index(reference)
            value_node = cell.find("x:v", _NS)
            value = value_node.text if value_node is not None and value_node.text else ""
            if cell.get("t") == "s" and value:
                value = shared[int(value)]
            elif cell.get("t") == "inlineStr":
                inline = cell.find("x:is", _NS)
                value = "".join(inline.itertext()) if inline is not None else ""
            values[column] = value
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])

    header_index = next(
        (index for index, row in enumerate(rows) if "Datum" in row and "Flurabstand [m]" in row),
        None,
    )
    if header_index is None:
        raise ElwasFormatError("ELWAS workbook has no water-level table")
    headers = rows[header_index]
    positions = {name: headers.index(name) for name in headers}
    required = {
        "Datum",
        "Wasserstand [m über NHN2016]",
        "Flurabstand [m]",
        "Geländeoberkante [m über NHN2016]",
    }
    if not required <= positions.keys():
        raise ElwasFormatError("ELWAS workbook is missing required columns")

    measurements: list[Measurement] = []
    for row in rows[header_index + 1 :]:
        raw_date = _cell(row, positions["Datum"])
        raw_depth = _cell(row, positions["Flurabstand [m]"])
        raw_level = _cell(row, positions["Wasserstand [m über NHN2016]"])
        raw_ground = _cell(row, positions["Geländeoberkante [m über NHN2016]"])
        if not raw_date or not raw_depth or not raw_level or not raw_ground:
            continue
        try:
            measured_on = date.fromisoformat(raw_date)
            measurements.append(
                Measurement(
                    measured_on=measured_on,
                    depth=_number(raw_depth),
                    groundwater_level=_number(raw_level),
                    ground_level=_number(raw_ground),
                    measuring_point_level=_optional_number(
                        _cell(row, positions.get("Messpunkthöhe [m über NHN2016]"))
                    ),
                    drawdown=_optional_number(_cell(row, positions.get("Abstich [m]"))),
                    note=_cell(row, positions.get("Hinweis")),
                )
            )
        except (ValueError, TypeError):
            continue
    if not measurements:
        raise ElwasFormatError(f"ELWAS workbook contains no values for {station_id}")
    title = rows[0][0] if rows and rows[0] else station_id
    station_name = title.split("(", 1)[0].strip() or station_id
    return station_name, sorted(measurements, key=lambda item: item.measured_on)


def calculate_statistics(
    station_id: str, station_name: str, measurements: list[Measurement]
) -> StationData:
    """Calculate robust trend and seasonal reference values."""
    series = sorted(measurements, key=lambda item: item.measured_on)
    latest = series[-1]
    trend_7 = _linear_trend(series, latest.measured_on, 7)
    trend_30 = _linear_trend(series, latest.measured_on, 30)
    direction_value = trend_30 if trend_30 is not None else trend_7
    if direction_value is None or abs(direction_value) < 0.5:
        direction = "stable"
    elif direction_value < 0:
        direction = "rising"
    else:
        direction = "falling"

    reference = [
        item.depth
        for item in series
        if item.measured_on.year < latest.measured_on.year
        and _circular_day_distance(item.measured_on, latest.measured_on) <= 15
    ]
    seasonal_mean = statistics.fmean(reference) if reference else None
    anomaly = latest.depth - seasonal_mean if seasonal_mean is not None else None
    percentile = (
        100 * sum(value <= latest.depth for value in reference) / len(reference)
        if reference
        else None
    )
    return StationData(
        station_id=station_id,
        station_name=station_name,
        latest=latest,
        measurement_count=len(series),
        series_start=series[0].measured_on,
        series_end=latest.measured_on,
        trend_7d_cm_week=trend_7,
        trend_30d_cm_week=trend_30,
        trend_direction=direction,
        seasonal_mean_depth=round(seasonal_mean, 3) if seasonal_mean is not None else None,
        seasonal_anomaly_depth=round(anomaly, 3) if anomaly is not None else None,
        seasonal_percentile=round(percentile, 1) if percentile is not None else None,
        long_term_mean_depth=round(statistics.fmean(item.depth for item in series), 3),
        long_term_mean_level=round(
            statistics.fmean(item.groundwater_level for item in series), 3
        ),
    )


def _linear_trend(series: list[Measurement], end: date, days: int) -> float | None:
    points = [item for item in series if 0 <= (end - item.measured_on).days <= days]
    if len(points) < 3:
        return None
    x = [(item.measured_on - points[0].measured_on).days for item in points]
    y = [item.depth for item in points]
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0:
        return None
    slope_m_day = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x, y, strict=True)
    ) / denominator
    return round(slope_m_day * 700, 2)


def _circular_day_distance(first: date, second: date) -> int:
    first_day = first.timetuple().tm_yday
    second_day = second.timetuple().tm_yday
    direct = abs(first_day - second_day)
    return min(direct, 366 - direct)


def _find_form(html: str, suffix: str) -> _Form:
    parser = _FormsParser()
    parser.feed(html)
    form = next((candidate for candidate in parser.forms if candidate.has_name_ending(suffix)), None)
    if form is None:
        raise ElwasFormatError(f"ELWAS form field {suffix} was not found")
    return form


def _find_form_with_control_value(html: str, value: str) -> _Form:
    parser = _FormsParser()
    parser.feed(html)
    form = next(
        (candidate for candidate in parser.forms if any(item[1] == value for item in candidate.controls)),
        None,
    )
    if form is None:
        raise StationNotFoundError(f"ELWAS result {value} was not found")
    return form


def _find_field_name(form: _Form, suffix: str) -> str:
    try:
        return next(name for name, _ in form.fields if name.endswith(suffix))
    except StopIteration as err:
        raise ElwasFormatError(f"ELWAS field {suffix} was not found") from err


def _find_jsf_form_id(form: _Form) -> str:
    """Return the real form identifier that Mojarra substitutes for @form."""
    form_id = next(
        (
            value
            for name, value in form.fields
            if name == value and name.endswith(":detail_form_id")
        ),
        None,
    )
    if form_id is None:
        raise ElwasFormatError("ELWAS detail form identifier was not found")
    return form_id


def _find_faces_namespace(form: _Form) -> str:
    """Detect whether the ELWAS server uses Jakarta Faces or legacy Javax Faces."""
    view_state_name = next(
        (name for name, _ in form.fields if name.endswith(".faces.ViewState")),
        None,
    )
    if view_state_name is None:
        raise ElwasFormatError("ELWAS Faces namespace was not found")
    return view_state_name.removesuffix(".ViewState")


def _find_control(form: _Form, marker: str) -> tuple[str, str, str]:
    control = next((item for item in form.controls if marker in item[0]), None)
    if control is None:
        raise ElwasFormatError(f"ELWAS control {marker} was not found")
    return control


def _replace_field(
    fields: list[tuple[str, str]], name: str, value: str
) -> list[tuple[str, str]]:
    return [(field_name, value if field_name == name else field_value) for field_name, field_value in fields]


def _extract_jsf_update(payload: str) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as err:
        raise ElwasFormatError("ELWAS returned invalid JSF data") from err
    updates = root.findall(".//update")
    html = next(
        (
            node.text
            for node in updates
            if node.get("id") in {"javax.faces.ViewRoot", "jakarta.faces.ViewRoot"}
        ),
        None,
    )
    if not html:
        html = "\n".join(node.text or "" for node in updates)
    if not html:
        raise ElwasFormatError("ELWAS did not return the requested detail view")
    return html


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def _cell(row: list[str], index: int | None) -> str:
    return row[index].strip() if index is not None and index < len(row) else ""


def _number(value: str) -> float:
    return float(value.replace(".", "").replace(",", ".")) if "," in value else float(value)


def _optional_number(value: str) -> float | None:
    return _number(value) if value else None
