import asyncio
import sys
import httpx
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from api.services.vegvesen import fetch_oslo_points

BASE_URL = "https://trafikkdata-api.atlas.vegvesen.no/"
START_YEAR = 2015

# Punkter vi vet har data fra 30-dagers hentingen
KNOWN_GOOD = [
    "17684V2460285", "16404V72814", "16405V72814", "13462V72813",
    "16406V72813", "16407V72813", "16408V72813", "16409V72813",
    "16410V72813", "16411V72813", "16412V72813", "16413V72813",
    "16414V72813", "16415V72813", "16416V72813", "16417V72813",
    "16418V72813", "16419V72813", "16420V72813", "16421V72813",
]

async def fetch_chunk(client, point_id, from_time, to_time):
    query = """
    query {
      trafficData(trafficRegistrationPointId: "%s") {
        volume {
          byHour(from: "%s", to: "%s") {
            edges {
              node {
                from to
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

    r = await client.post(
        BASE_URL,
        json={"query": query},
        headers={"Content-Type": "application/json"}
    )
    data = r.json()
    return (
        data.get("data", {})
            .get("trafficData", {})
            .get("volume", {})
            .get("byHour", {})
            .get("edges", [])
    )


async def point_has_data(client, point_id) -> bool:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    try:
        edges = await fetch_chunk(client, point_id, week_ago, now)
        return len(edges) > 0
    except:
        return False


async def fetch_full_history(client, point_id, name, lat, lon):
    start = datetime(START_YEAR, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    all_rows = []
    current = start

    while current < end:
        chunk_end = min(current + timedelta(hours=100), end)
        try:
            edges = await fetch_chunk(client, point_id, current, chunk_end)
            for edge in edges:
                node = edge["node"]
                all_rows.append({
                    "point_id": point_id,
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "from": node["from"],
                    "to": node["to"],
                    "volume": node["total"]["volumeNumbers"]["volume"],
                    "coverage": node["total"]["coverage"]["percentage"],
                })
        except:
            pass
        current = chunk_end
        await asyncio.sleep(0.05)

    return all_rows


async def main():
    print("Henter punktliste...")
    points = await fetch_oslo_points()

    print("Filtrerer ut tomme punkter...")
    path = Path("data/raw/vegvesen")
    path.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=30) as client:
        good_points = []
        for i, point in enumerate(points):
            has_data = await point_has_data(client, point["id"])
            status = "OK" if has_data else "tom"
            print(f"  [{i+1}/{len(points)}] {point['name']}: {status}")
            if has_data:
                good_points.append(point)

    print(f"\n{len(good_points)} punkter med data funnet!")
    print("Starter historisk henting...\n")

    async with httpx.AsyncClient(timeout=30) as client:
        for i, point in enumerate(good_points):
            point_id = point["id"]
            name = point["name"]
            lat = point["location"]["coordinates"]["latLon"]["lat"]
            lon = point["location"]["coordinates"]["latLon"]["lon"]

            filename = path / f"history_{point_id}.csv"
            if filename.exists():
                print(f"[{i+1}/{len(good_points)}] {name}: allerede hentet, hopper over")
                continue

            rows = await fetch_full_history(client, point_id, name, lat, lon)

            if rows:
                df = pd.DataFrame(rows)
                df.to_csv(filename, index=False)
                print(f"[{i+1}/{len(good_points)}] {name}: {len(rows)} timer lagret")
            else:
                print(f"[{i+1}/{len(good_points)}] {name}: ingen data")

    print("\nFerdig! All historikk lagret i data/raw/vegvesen/")

asyncio.run(main())