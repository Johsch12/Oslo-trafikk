import httpx
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://trafikkdata-api.atlas.vegvesen.no/"

POINTS_QUERY = """
{
  trafficRegistrationPoints(searchQuery: {
    roadCategoryIds: [E, R, F]
    countyNumbers: [3]
  }) {
    id
    name
    location {
      coordinates {
        latLon { lat lon }
      }
    }
  }
}
"""

async def fetch_oslo_points() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": POINTS_QUERY},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
    points = data.get("data", {}).get("trafficRegistrationPoints", [])
    print(f"Fant {len(points)} malepunkter i Oslo")
    return points

async def fetch_traffic(point_id: str, from_time: datetime, to_time: datetime) -> list:
    query = """
    query {
      trafficData(trafficRegistrationPointId: "%s") {
        volume {
          byHour(from: "%s", to: "%s") {
            edges {
              node {
                from
                to
                total {
                  volumeNumbers { volume }
                  coverage { percentage }
                }
              }
            }
          }
        }
      }
    }
    """ % (point_id, from_time.isoformat(), to_time.isoformat())

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

    edges = (
        data.get("data", {})
            .get("trafficData", {})
            .get("volume", {})
            .get("byHour", {})
            .get("edges", [])
    )
    rows = []
    for edge in edges:
        node = edge["node"]
        rows.append({
            "point_id": point_id,
            "from": node["from"],
            "to": node["to"],
            "volume": node["total"]["volumeNumbers"]["volume"],
            "coverage": node["total"]["coverage"]["percentage"],
        })
    return rows

async def fetch_all_points(days_back: int = 7) -> pd.DataFrame:
    points = await fetch_oslo_points()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=days_back)
    all_rows = []
    for point in points:
        point_id = point["id"]
        name = point["name"]
        lat = point["location"]["coordinates"]["latLon"]["lat"]
        lon = point["location"]["coordinates"]["latLon"]["lon"]
        try:
            rows = await fetch_traffic(point_id, from_time, to_time)
            for row in rows:
                row["name"] = name
                row["lat"] = lat
                row["lon"] = lon
            all_rows.extend(rows)
            print(f"Hentet {len(rows)} rader fra {name}")
        except Exception as e:
            print(f"Feil ved {name}: {e}")
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["from"] = pd.to_datetime(df["from"])
        df["to"] = pd.to_datetime(df["to"])
    return df

def save_raw(df: pd.DataFrame):
    path = Path("data/raw/vegvesen")
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"traffic_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False)
    print(f"Lagret {len(df)} rader til {filename}")
    return filename