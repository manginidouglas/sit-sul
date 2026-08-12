from urllib.parse import parse_qs, urlparse
import pytest
from ice_sul.routing import Coordinate, OSRMClient


def route_transport(url, timeout):
    assert "/route/v1/driving/-49.2700000,-25.4300000;-49.1700000,-25.5300000" in url
    assert parse_qs(urlparse(url).query) == {"overview": ["false"], "steps": ["false"]}
    return {"code":"Ok", "routes":[{"duration":1200,"distance":18000}], "waypoints":[{"location":[-49.269,-25.431],"distance":0.0},{"location":[-49.171,-25.529],"distance":812.5}]}


def test_route_converts_units_and_reports_snapping():
    result = OSRMClient(transport=route_transport).route(Coordinate(-25.43,-49.27), Coordinate(-25.53,-49.17))
    assert result.ok and result.duration_minutes == 20 and result.distance_meters == 18000
    assert result.snapped_origin == Coordinate(-25.431,-49.269)
    assert result.origin_snap_distance_meters == 0.0
    assert result.destination_snap_distance_meters == 812.5


def test_route_detects_osrm_failure():
    client = OSRMClient(transport=lambda *_: {"code":"NoRoute", "message":"Impossible route"})
    result = client.route(Coordinate(-25,-49), Coordinate(-26,-50))
    assert not result.ok and "NoRoute" in result.error


def test_table_batch_units_nulls_and_indices():
    def transport(url, timeout):
        query = parse_qs(urlparse(url).query)
        assert query["sources"] == ["0;1"] and query["destinations"] == ["2;3"]
        assert query["annotations"] == ["duration,distance"]
        return {"code":"Ok", "durations":[[60,None],[120,180]], "distances":[[1000,None],[2000,3000]],
                "sources":[{"location":[-49,-25],"distance":2.5},{"location":[-50,-26]}],
                "destinations":[{"location":[-51,-27],"distance":900},{"location":[-52,-28],"distance":0}]}
    points = [Coordinate(-25,-49), Coordinate(-26,-50), Coordinate(-27,-51), Coordinate(-28,-52)]
    result = OSRMClient(transport=transport).table(points[:2], points[2:])
    assert result.durations_minutes == [[1,None],[2,3]]
    assert result.distances_meters == [[1000,None],[2000,3000]]
    assert result.source_snap_distances_meters == [2.5, None]
    assert result.destination_snap_distances_meters == [900, 0]


def test_table_chunks_obeys_cell_limit():
    calls=[]
    client=OSRMClient()
    client.table=lambda sources,destinations,distances=False: calls.append((len(sources),len(destinations))) or object()
    chunks=list(client.table_chunks([Coordinate(-25,-49)]*3,[Coordinate(-26,-50)]*8,max_cells=12))
    assert [(a,b) for a,b,_ in chunks] == [(0,4),(4,8)]
    assert calls == [(3,4),(3,4)]


def test_coordinate_validation_and_empty_table():
    with pytest.raises(ValueError): Coordinate(91, 0)
    with pytest.raises(ValueError): OSRMClient().table([], [Coordinate(0,0)])


def test_route_snap_distance_is_none_when_waypoint_field_absent():
    payload = {"code": "Ok", "routes": [{"duration": 60, "distance": 100}],
               "waypoints": [{"location": [-49, -25]}, {"location": [-50, -26]}]}
    result = OSRMClient(transport=lambda *_: payload).route(Coordinate(-25, -49), Coordinate(-26, -50))
    assert result.snapped_origin == Coordinate(-25, -49)
    assert result.origin_snap_distance_meters is None
    assert result.destination_snap_distance_meters is None
