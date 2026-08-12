"""Small, dependency-free client for a self-hosted OSRM HTTP service."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class Coordinate:
    """A WGS84 coordinate. OSRM serializes longitude before latitude."""
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("coordinate outside WGS84 bounds")

    def osrm(self) -> str:
        return f"{self.longitude:.7f},{self.latitude:.7f}"


@dataclass(frozen=True)
class RouteResult:
    ok: bool
    duration_minutes: float | None = None
    distance_meters: float | None = None
    snapped_origin: Coordinate | None = None
    snapped_destination: Coordinate | None = None
    error: str | None = None


@dataclass(frozen=True)
class MatrixResult:
    durations_minutes: list[list[float | None]]
    distances_meters: list[list[float | None]] | None
    sources: list[Coordinate | None]
    destinations: list[Coordinate | None]


class RoutingError(RuntimeError):
    """OSRM was unavailable or returned an invalid response."""


Transport = Callable[[str, float], dict]


def _http_json(url: str, timeout: float) -> dict:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - configured local endpoint
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RoutingError(f"OSRM request failed: {exc}") from exc


def _location(value: dict | None) -> Coordinate | None:
    if not value or value.get("location") is None:
        return None
    longitude, latitude = value["location"]
    return Coordinate(latitude=latitude, longitude=longitude)


class OSRMClient:
    """Client for OSRM route/table APIs; intended for a local Brazil instance."""

    def __init__(self, base_url: str = "http://127.0.0.1:5000", *, timeout: float = 60, transport: Transport = _http_json):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def _get(self, path: str, params: dict[str, str]) -> dict:
        payload = self._transport(f"{self.base_url}{path}?{urlencode(params)}", self.timeout)
        if payload.get("code") != "Ok":
            raise RoutingError(f"OSRM {payload.get('code', 'invalid response')}: {payload.get('message', '')}".rstrip())
        return payload

    def route(self, origin: Coordinate, destination: Coordinate) -> RouteResult:
        try:
            data = self._get(f"/route/v1/driving/{origin.osrm()};{destination.osrm()}", {"overview": "false", "steps": "false"})
            if not data.get("routes"):
                return RouteResult(ok=False, error="NoRoute")
            route = data["routes"][0]
            waypoints = data.get("waypoints", [])
            return RouteResult(
                ok=True,
                duration_minutes=route["duration"] / 60,
                distance_meters=route["distance"],
                snapped_origin=_location(waypoints[0]) if len(waypoints) > 0 else None,
                snapped_destination=_location(waypoints[1]) if len(waypoints) > 1 else None,
            )
        except RoutingError as exc:
            return RouteResult(ok=False, error=str(exc))

    def table(self, sources: Sequence[Coordinate], destinations: Sequence[Coordinate], *, distances: bool = True) -> MatrixResult:
        if not sources or not destinations:
            raise ValueError("sources and destinations must not be empty")
        coordinates = [*sources, *destinations]
        source_ids = ";".join(map(str, range(len(sources))))
        destination_ids = ";".join(map(str, range(len(sources), len(coordinates))))
        annotations = "duration,distance" if distances else "duration"
        data = self._get(
            "/table/v1/driving/" + ";".join(point.osrm() for point in coordinates),
            {"sources": source_ids, "destinations": destination_ids, "annotations": annotations},
        )
        durations = [[None if value is None else value / 60 for value in row] for row in data["durations"]]
        distance_rows = data.get("distances")
        return MatrixResult(
            durations_minutes=durations,
            distances_meters=distance_rows,
            sources=[_location(item) for item in data.get("sources", [])],
            destinations=[_location(item) for item in data.get("destinations", [])],
        )

    def table_chunks(self, sources: Sequence[Coordinate], destinations: Sequence[Coordinate], *, max_cells: int = 10_000, distances: bool = False) -> Iterable[tuple[int, int, MatrixResult]]:
        """Yield destination chunks without exceeding the configured OSRM cell limit."""
        if not sources or max_cells < len(sources):
            raise ValueError("max_cells must accommodate at least one destination")
        width = max(1, max_cells // len(sources))
        for start in range(0, len(destinations), width):
            stop = min(start + width, len(destinations))
            yield start, stop, self.table(sources, destinations[start:stop], distances=distances)
