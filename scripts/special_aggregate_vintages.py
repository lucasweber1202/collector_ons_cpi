"""Discover archived MM23 snapshots needed for January special-aggregate weights.

From 2017 onward ONS uses two CPI higher-level weight updates each year. The
current MM23 annual weight eventually represents the February-December regime.
The final January-regime value is preserved in the MM23 version that is
superseded by the scheduled March release. This module discovers those archived
snapshots without persisting anything.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin

from scripts.special_aggregates import MM23SpecialPanel, parse_mm23_special_aggregates

MM23_VERSIONS_URL = (
    "https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices/"
    "current"
)
DOUBLE_WEIGHT_START_YEAR = 2017


@dataclass(frozen=True)
class MM23Snapshot:
    """One archived full-MM23 CSV and the date on which ONS superseded it."""

    version_id: str
    csv_url: str
    superseded_at: datetime
    reason: str


class _TableRows(HTMLParser):
    """Capture text and links for each HTML table row without external parsers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, list[str]]] = []
        self._in_row = False
        self._text: list[str] = []
        self._hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._in_row = True
            self._text = []
            self._hrefs = []
            return
        if not self._in_row or tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self._hrefs.append(value)

    def handle_data(self, data: str) -> None:
        if self._in_row:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "tr" or not self._in_row:
            return
        self.rows.append((" ".join(self._text), list(self._hrefs)))
        self._in_row = False
        self._text = []
        self._hrefs = []


_DATE_RE = re.compile(r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}\s+\d{2}:\d{2})")
_VERSION_RE = re.compile(r"/previous/(v\d+)/mm23\.csv(?:$|[?&#])", re.IGNORECASE)


def _snapshot_reason(row_text: str) -> str:
    lowered = row_text.lower()
    if "scheduled update/revision" in lowered:
        return "scheduled"
    if "correction" in lowered:
        return "correction"
    return "other"


def parse_mm23_snapshot_index(page_html: str) -> list[MM23Snapshot]:
    """Parse versioned full-MM23 CSV links from the official dataset history page."""
    parser = _TableRows()
    parser.feed(page_html)
    snapshots: list[MM23Snapshot] = []
    seen_versions: set[str] = set()
    for row_text, hrefs in parser.rows:
        date_match = _DATE_RE.search(row_text)
        if date_match is None:
            continue
        superseded_at = datetime.strptime(date_match.group(1), "%d %B %Y %H:%M")
        csv_candidates: list[tuple[str, str]] = []
        for raw_href in hrefs:
            href = html.unescape(raw_href)
            decoded = unquote(href)
            version_match = _VERSION_RE.search(decoded)
            if version_match is not None:
                csv_candidates.append((version_match.group(1).lower(), href))
        if not csv_candidates:
            continue
        if len(csv_candidates) != 1:
            raise ValueError(
                f"MM23 history row for {superseded_at.date()} has {len(csv_candidates)} CSV links"
            )
        version_id, href = csv_candidates[0]
        if version_id in seen_versions:
            raise ValueError(f"MM23 history publishes duplicate version {version_id}")
        seen_versions.add(version_id)
        snapshots.append(
            MM23Snapshot(
                version_id=version_id,
                csv_url=urljoin(MM23_VERSIONS_URL, href),
                superseded_at=superseded_at,
                reason=_snapshot_reason(row_text),
            )
        )
    if not snapshots:
        raise ValueError("ONS MM23 history page contains no versioned CSV snapshots")
    return sorted(snapshots, key=lambda snapshot: snapshot.superseded_at)


def january_regime_snapshots(
    snapshots: list[MM23Snapshot],
    start_year: int = DOUBLE_WEIGHT_START_YEAR,
) -> dict[int, MM23Snapshot]:
    """Select the final January-weight snapshot for each double-update year.

    The target is the version superseded by the *scheduled* March release. A
    same-day correction is deliberately not a selector because it belongs to
    the newly released February-December regime rather than the preceding
    January regime.
    """
    selected: dict[int, MM23Snapshot] = {}
    for snapshot in snapshots:
        year = snapshot.superseded_at.year
        if year < start_year or snapshot.superseded_at.month != 3:
            continue
        if snapshot.reason != "scheduled":
            continue
        if year in selected:
            raise ValueError(f"Two scheduled March MM23 snapshots found for {year}")
        selected[year] = snapshot
    return selected


def discover_mm23_snapshots() -> list[MM23Snapshot]:
    """Fetch and parse the official full-MM23 previous-version index."""
    from scripts.extract import build_client, http_get

    with build_client() as client:
        response = http_get(client, MM23_VERSIONS_URL)
    return parse_mm23_snapshot_index(response.text)


def collect_mm23_snapshot(snapshot: MM23Snapshot) -> MM23SpecialPanel:
    """Download one archived full-MM23 CSV through the collector HTTP policy."""
    from scripts.extract import build_client, http_get

    with build_client() as client:
        response = http_get(client, snapshot.csv_url)
    return parse_mm23_special_aggregates(response.content)
