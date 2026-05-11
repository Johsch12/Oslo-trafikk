import httpx

BASE_URL = "https://api.entur.io/journey-planner/v3/graphql"
HEADERS = {
    "ET-Client-Name": "oslo-trafikk",
    "Content-Type": "application/json"
}

TRIP_QUERY = """
query Trip($from_lat: Float!, $from_lon: Float!, $to_lat: Float!, $to_lon: Float!, $when: DateTime!) {
  trip(
    from: { coordinates: { latitude: $from_lat, longitude: $from_lon } }
    to: { coordinates: { latitude: $to_lat, longitude: $to_lon } }
    dateTime: $when
    numTripPatterns: 3
  ) {
    tripPatterns {
      duration
      legs {
        mode
        line { publicCode }
        fromPlace { name }
        toPlace { name }
      }
    }
  }
}
"""

async def fetch_transit_trip(from_lat, from_lon, to_lat, to_lon, when: str) -> list:
    variables = {
        "from_lat": from_lat,
        "from_lon": from_lon,
        "to_lat": to_lat,
        "to_lon": to_lon,
        "when": when
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": TRIP_QUERY, "variables": variables},
            headers=HEADERS
        )
        data = response.json()
    patterns = data.get("data", {}).get("trip", {}).get("tripPatterns", [])
    results = []
    for p in patterns:
        modes = [leg["mode"] for leg in p["legs"]]
        results.append({
            "duration_seconds": p["duration"],
            "duration_minutes": round(p["duration"] / 60),
            "modes": modes,
        })
    return results