import httpx
import asyncio
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("FROST_CLIENT_ID")

BLINDERN = "SN18700"
ELEMENTS = "air_temperature,sum(precipitation_amount PT1H),wind_speed"

async def fetch_chunk(from_dt: datetime, to_dt: datetime) -> list:
    url = "https://frost.met.no/observations/v0.jsonld"
    params = {
        "sources": BLINDERN,
        "elements": ELEMENTS,
        "referencetime": f"{from_dt.isoformat()}/{to_dt.isoformat()}",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, params=params, auth=(CLIENT_ID, ""))
        if r.status_code != 200:
            return []
        return r.json().get("data", [])

def parse_observations(data: list) -> list:
    rows = []
    grouped = {}
    for obs in data:
        time = obs["referenceTime"]
        if time not in grouped:
            grouped[time] = {"time": time}
        for elem in obs["observations"]:
            eid = elem["elementId"]
            val = elem["value"]
            if "temperature" in eid:
                grouped[time]["temperature"] = val
            elif "precipitation" in eid:
                grouped[time]["precipitation"] = val
            elif "wind" in eid:
                grouped[time]["wind_speed"] = val
    return list(grouped.values())

async def main():
    start = datetime(2015, 1, 1)
    end = datetime.now()
    chunk_days = 30
    all_rows = []
    current = start
    total_chunks = (end - start).days // chunk_days + 1

    print(f"Henter vær fra Blindern 2015 til nå ({total_chunks} chunks)...")

    i = 0
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        data = await fetch_chunk(current, chunk_end)
        rows = parse_observations(data)
        all_rows.extend(rows)
        i += 1
        if i % 10 == 0:
            print(f"  [{i}/{total_chunks}] {current.date()} — {len(all_rows)} rader så langt")
        current = chunk_end
        await asyncio.sleep(0.2)

    df = pd.DataFrame(all_rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)

    path = Path("data/raw/met")
    path.mkdir(parents=True, exist_ok=True)
    filename = path / "weather_blindern_2015_2026.csv"
    df.to_csv(filename, index=False)
    print(f"\nFerdig! Lagret {len(df)} timer til {filename}")

asyncio.run(main())