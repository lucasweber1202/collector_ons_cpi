"""Download and parse official ONS UK CPI index levels and basket weights."""

from __future__ import annotations

import html
import io
import logging
import math
import re
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import httpx
import pandas as pd

from scripts.config import (
    BACKOFF_FACTOR,
    DOWNLOAD_DELAY,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "Office for National Statistics"
RELEASE_NAME = "Consumer Prices Index"
COUNTRY_CURRENCY = "GBP"
SOURCE_URL = (
    "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceinflation"
)
WEIGHTS_PAGE_URL = (
    "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/"
    "consumerpriceinflationupdatingweightsannexatablesw1tow3"
)
CPI_DOWNLOAD_URL = (
    "https://www.ons.gov.uk/file?uri=%2Feconomy%2Finflationandpriceindices%2Fdatasets%2F"
    "consumerpriceinflation%2Fcurrent%2Fconsumerpriceinflationdetailedreferencetables.xlsx"
)

# Explicit W1 combined/split classifications verified against Table 38 CDIDs.
W1_ALIASES = {
    "05.3.1/2": "D7E3",
    "06.1.2/3": "D7F8",
    "06.2.1/3": "D7FA",
    "07.1.1A": "D7E8",
    "07.1.1B": "D7E9",
    "07.1.2/3": "D7EA",
    "07.3.2/6": "D7EG",
    "08.2/3": "D7EM",
    "09.2.1/2/3": "D7FD",
    "09.3.4/5": "D7EU",
    "09.5.3/4": "D7FM",
    "12.1.2/3": "D7EZ",
    "12.5.3/5": "D7EQ",
}
_ORIGINAL_WEIGHTS: dict[date, dict[str, float]] = {}
_ORIGINAL_WEIGHT_CATALOG: dict[str, dict[str, str]] = {}


def get_original_weights() -> dict[date, dict[str, float]]:
    """Return source-published weights, including weight-only subclasses."""
    return {month: dict(values) for month, values in _ORIGINAL_WEIGHTS.items()}


def get_original_weight_catalog() -> dict[str, dict[str, str]]:
    """Return original classification labels and explicit Table 38 mappings."""
    return {key: dict(value) for key, value in _ORIGINAL_WEIGHT_CATALOG.items()}


ECO_GROUPS = frozenset({"consumer_prices"})
UNITS = frozenset({"index"})
FREQUENCIES = frozenset({"monthly"})
ALLOWED_HOSTS = frozenset({"www.ons.gov.uk", "ons.gov.uk"})

_SERIES_CATALOG: dict[str, dict[str, str]] = {}
_LAST_PUBLISH_DATE: date | None = None


def _slug(value: object) -> str:
    """Normalize an ONS label into a stable uppercase ID component."""
    value = str(value).upper().replace("&", " AND ")
    value = re.sub(r"\(NEC\)|N\.E\.C\.?", " NEC ", value)
    value = re.sub(r"[^A-Z0-9]+", "_", value).strip("_")
    return re.sub(r"_+", "_", value)


def _node_token(raw_code: object) -> tuple[str, str]:
    """Return hierarchy family and normalized node token from an ONS code."""
    value = str(raw_code).strip()
    if value in {"0", "0.0"}:
        return "COICOP", "ALL"
    if value.lower().startswith("agg"):
        number = re.sub(r"\D", "", value)
        return "ALT", f"A{int(number):02d}"
    value = value.replace(".0", "") if re.fullmatch(r"\d+\.0", value) else value
    digits = re.sub(r"\D", "", value)
    depth = value.count(".") + 1
    if depth == 1:
        return "COICOP", f"D{int(digits):02d}"
    if depth == 2:
        return "COICOP", f"G{digits.zfill(3)}"
    return "COICOP", f"C{digits}"


def _make_series_id(family: str, node: str, native_id: str, name: object) -> str:
    """Build a structured series identifier from official workbook fields."""
    series_id = f"CPI_{family}_{node}_{native_id.strip().upper()}_{_slug(name)}"
    if len(series_id) > 200:
        raise ValueError(f"series_id exceeds 200 characters: {series_id}")
    return series_id


def parse_series_id(series_id: str) -> tuple[str, str, str, str, str]:
    """Decode ``CPI_{family}_{node}_{native_id}_{official_name_slug}``."""
    parts = series_id.split("_", 4)
    if len(parts) != 5 or parts[0] != "CPI" or parts[1] not in {"COICOP", "ALT"}:
        raise ValueError(f"Invalid UK CPI series_id: {series_id}")
    measure, family, node, native_id, name_slug = parts
    if not node or not native_id or not name_slug:
        raise ValueError(f"Incomplete UK CPI series_id: {series_id}")
    return measure, family, node, native_id, name_slug


def get_series_catalog() -> dict[str, dict[str, str]]:
    """Return a defensive copy of source metadata discovered during extraction."""
    return {series_id: fields.copy() for series_id, fields in _SERIES_CATALOG.items()}


def get_last_publish_date() -> date | None:
    """Return the release date parsed from the current ONS workbook."""
    return _LAST_PUBLISH_DATE


def _build_client() -> httpx.Client:
    """Build the single managed HTTP client used by a collection call."""
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        trust_env=True,
        follow_redirects=False,
    )


def _http_get(client: httpx.Client, url: str, method: str = "GET") -> httpx.Response:
    """Request an allowlisted ONS URL with bounded exponential-backoff retries."""
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Refusing non-ONS URL: {url}")
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.request(method, url)
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError(
                f"retryable status {response.status_code}",
                request=response.request,
                response=response,
            )
        except httpx.TransportError as exc:
            last_error = exc
        if attempt < MAX_RETRIES:
            delay = BACKOFF_FACTOR**attempt
            logger.warning(
                "ONS request failed; retrying in %.1fs (%d/%d)", delay, attempt + 1, MAX_RETRIES
            )
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def _latest_weights_url(page_html: str) -> str:
    """Discover the current W1-W3 workbook URL from the official dataset page."""
    matches = re.findall(
        r'href="([^"]*annexa[^"?]*weights\d{4}[^"?]*\.xlsx[^"]*)"',
        page_html,
        re.IGNORECASE,
    )
    if not matches:
        matches = re.findall(r'href="([^"]*\.xlsx[^"]*)"', page_html, re.IGNORECASE)
    if not matches:
        raise ValueError("ONS weights page contains no XLSX download link")
    return urljoin(WEIGHTS_PAGE_URL, html.unescape(matches[0]))


def _excel_frame(blob: bytes, sheet_name: str) -> pd.DataFrame:
    """Read one workbook sheet without treating source rows as headers."""
    return pd.read_excel(io.BytesIO(blob), sheet_name=sheet_name, header=None, engine="openpyxl")


def _publication_date(blob: bytes) -> date | None:
    """Parse the source-stamped publication date from the contents sheet."""
    contents = _excel_frame(blob, "Contents")
    for value in contents.iloc[:, 0].dropna().astype(str):
        match = re.search(r"Publication date:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", value)
        if match:
            parsed = time.strptime(match.group(1), "%d %B %Y")
            return date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday)
    return None


def parse_cpi_workbook(
    blob: bytes, start_date: date | None = None
) -> dict[date, dict[str, float | None]]:
    """Parse all ONS CPI detailed index levels from workbook Table 38."""
    global _LAST_PUBLISH_DATE
    frame = _excel_frame(blob, "Table 38")
    catalog: dict[str, dict[str, str]] = {}
    column_ids: dict[int, str] = {}
    for column in range(2, len(frame.columns)):
        raw_code = frame.iat[4, column]
        native = frame.iat[5, column]
        name = frame.iat[6, column]
        if pd.isna(raw_code) or pd.isna(native) or pd.isna(name):
            continue
        family, node = _node_token(raw_code)
        series_id = _make_series_id(family, node, str(native), name)
        column_ids[column] = series_id
        catalog[series_id] = {
            "family": family,
            "node": node,
            "native_id": str(native).strip().upper(),
            "name": str(name).strip(),
        }

    parsed: dict[date, dict[str, float | None]] = {}
    for row in range(7, len(frame.index)):
        raw_date = frame.iat[row, 1]
        if pd.isna(raw_date):
            continue
        try:
            ref_date = pd.Timestamp(raw_date).date().replace(day=1)
        except (TypeError, ValueError):
            continue
        if start_date and ref_date < start_date.replace(day=1):
            continue
        values: dict[str, float | None] = {}
        for column, series_id in column_ids.items():
            raw_value = frame.iat[row, column]
            if pd.isna(raw_value):
                values[series_id] = None
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                values[series_id] = None
                continue
            values[series_id] = value if math.isfinite(value) else None
        if values:
            parsed[ref_date] = values

    if not parsed:
        raise ValueError("Table 38 contained no usable CPI observations")
    _SERIES_CATALOG.clear()
    _SERIES_CATALOG.update(catalog)
    _LAST_PUBLISH_DATE = _publication_date(blob)
    logger.info(
        "Parsed %d CPI series across %d months (%s to %s)",
        len(catalog),
        len(parsed),
        min(parsed),
        max(parsed),
    )
    return parsed


def _weight_header(raw: object) -> tuple[int, tuple[int, ...]] | None:
    """Decode a W1 year/regime header into the months in which it applies."""
    if isinstance(raw, (int, float)) and not pd.isna(raw):
        year = int(raw)
        return year, tuple(range(1, 13))
    text = str(raw).replace("\n", " ").strip()
    match = re.search(r"(20\d{2})", text)
    if not match:
        return None
    year = int(match.group(1))
    return (year, (1,)) if "Jan" in text and "Feb" not in text else (year, tuple(range(2, 13)))


def _weight_code_name(raw_name: object) -> tuple[str, str] | None:
    """Split a W1 label into a classification code and official name."""
    text = str(raw_name).strip()
    match = re.match(r"^(\d{1,2}(?:\.\d+(?:/\d+)*)*(?:[AB])?)\s+(.+)$", text)
    if match:
        code = match.group(1)
        return code, match.group(2).strip()
    if text.lower() in {"all goods", "all services"}:
        return text.upper().replace(" ", ""), text
    if "overall index" in text.lower():
        return "0", text
    return None


def _match_weight_series(code: str, name: str, catalog: dict[str, dict[str, str]]) -> str | None:
    """Use exact classification or reviewed CDID aliases, never fuzzy matching."""
    if code.count(".") > 2 or code in {"ALLGOODS", "ALLSERVICES"}:
        return None
    family, node = _node_token(code)
    native_id = W1_ALIASES.get(code)
    candidates = [
        series_id
        for series_id, fields in catalog.items()
        if fields["family"] == family
        and (fields["native_id"] == native_id if native_id else fields["node"] == node)
    ]
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous W1 mapping: {code} {name}: {candidates}")
    if native_id and not candidates:
        raise ValueError(f"Reviewed W1 alias {code} requires missing CDID {native_id}")
    return candidates[0] if candidates else None


def parse_weights_workbook(
    blob: bytes,
    catalog: dict[str, dict[str, str]],
    start_date: date | None = None,
) -> dict[date, dict[str, float]]:
    """Parse official W1 CPI weights and expand each annual regime by month."""
    _ORIGINAL_WEIGHTS.clear()
    _ORIGINAL_WEIGHT_CATALOG.clear()
    originals: dict[date, dict[str, float]] = {}
    original_catalog: dict[str, dict[str, str]] = {}
    frame = _excel_frame(blob, "W1-CPI")
    headers = {
        column: _weight_header(frame.iat[4, column]) for column in range(3, len(frame.columns))
    }
    parsed: dict[date, dict[str, float]] = {}
    matched: set[str] = set()
    claimed_by: dict[str, tuple[str, str]] = {}
    unmatched = 0
    conflicts = 0
    for row in range(5, len(frame.index)):
        label = _weight_code_name(frame.iat[row, 2])
        if label is None:
            continue
        series_id = _match_weight_series(label[0], label[1], catalog)
        original_id = "CPI_W1_" + label[0].replace(".", "P").replace("/", "S")
        original_catalog[original_id] = {
            "code": label[0],
            "name": label[1],
            "mapped_series_id": series_id or "",
        }
        if series_id is None:
            # An official weight we cannot attribute is a reconciliation gap, not
            # noise: report it instead of dropping the row silently.
            unmatched += 1
            logger.warning(
                "W1 row %d matched no Table 38 series: code=%s name=%s",
                row,
                label[0],
                label[1],
            )
        if series_id in claimed_by and claimed_by[series_id] != label:
            # Two official rows describing one series is a mapping the last
            # write would otherwise resolve silently.
            logger.warning(
                "W1 rows code=%s name=%s and code=%s name=%s both map to %s",
                *claimed_by[series_id],
                *label,
                series_id,
            )
        if series_id is not None:
            claimed_by[series_id] = label
            matched.add(series_id)
        for column, header in headers.items():
            if header is None:
                continue
            raw_weight = frame.iat[row, column]
            try:
                weight = float(raw_weight)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(weight):
                continue
            if weight < 0:
                raise ValueError(f"Negative W1 weight: {label}")
            year, months = header
            for month in months:
                ref_date = date(year, month, 1)
                if start_date and ref_date < start_date.replace(day=1):
                    continue
                original_month = originals.setdefault(ref_date, {})
                if original_id in original_month and original_month[original_id] != weight:
                    raise ValueError(f"Conflicting W1 weights for {original_id} at {ref_date}")
                original_month[original_id] = weight
                if series_id is None:
                    continue
                previous = parsed.setdefault(ref_date, {}).get(series_id)
                if previous is not None and previous != weight:
                    # Duplicate rows agreeing on a value are harmless; disagreeing
                    # ones mean the stored weight depends on workbook row order.
                    conflicts += 1
                    raise ValueError(
                        f"Conflicting W1 weights for {series_id} at {ref_date}: "
                        f"{previous!r} then {weight!r} (row {row}, code={label[0]})"
                    )
                parsed[ref_date][series_id] = weight
    if not parsed:
        raise ValueError("W1-CPI contained no usable weights")
    logger.info(
        "Parsed weights for %d/%d CPI series across %d months "
        "(%d W1 rows unmatched, %d conflicting values)",
        len(matched),
        len(catalog),
        len(parsed),
        unmatched,
        conflicts,
    )
    _ORIGINAL_WEIGHTS.update(originals)
    _ORIGINAL_WEIGHT_CATALOG.update(original_catalog)
    return parsed


def get_workbook_fingerprint() -> str | None:
    """Return the CPI workbook's current entity tag without downloading its body.

    Release polling compares this between attempts, so an unchanged workbook
    costs one header request instead of a full download and parse. Returns
    ``None`` when the source exposes no validator, which makes the caller fall
    back to downloading rather than risk missing a release.
    """
    with _build_client() as client:
        response = _http_get(client, CPI_DOWNLOAD_URL, method="HEAD")
    return response.headers.get("etag")


def collect_raw_data(start_date: date | None = None) -> dict[date, dict[str, float | None]]:
    """Download current official CPI workbook and return standardized observations."""
    with _build_client() as client:
        response = _http_get(client, CPI_DOWNLOAD_URL)
    return parse_cpi_workbook(response.content, start_date)


def collect_weights(start_date: date | None = None) -> dict[date, dict[str, float]]:
    """Discover and download the latest official W1-W3 weights workbook."""
    if not _SERIES_CATALOG:
        raise RuntimeError("collect_raw_data must run before collect_weights")
    with _build_client() as client:
        page = _http_get(client, WEIGHTS_PAGE_URL)
        weights_url = _latest_weights_url(page.text)
        if DOWNLOAD_DELAY:
            time.sleep(DOWNLOAD_DELAY)
        workbook = _http_get(client, weights_url)
    return parse_weights_workbook(workbook.content, get_series_catalog(), start_date)
