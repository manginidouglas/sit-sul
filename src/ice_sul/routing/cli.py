"""Command-line access to the local OSRM instance."""
import argparse
from dataclasses import asdict
import json
from .client import Coordinate, OSRMClient


def point(text: str) -> Coordinate:
    try:
        latitude, longitude = map(float, text.split(","))
        return Coordinate(latitude, longitude)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use LATITUDE,LONGITUDE") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the self-hosted SIT OSRM service")
    parser.add_argument("origin", type=point)
    parser.add_argument("destination", type=point)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    result = OSRMClient(args.url).route(args.origin, args.destination)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 2

if __name__ == "__main__":
    raise SystemExit(main())
