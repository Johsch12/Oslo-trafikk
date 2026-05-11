import httpx
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
HEADERS = {"User-Agent": "oslo-trafikk/1.0 github.com/Johsch12/Oslo-trafikk"}

async def fetch_weather(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            BASE_URL,
            params={"lat": round(lat, 4), "lon": round(lon, 4)},
            headers=HEADERS
        )
        response.raise_for_status()
        return response.json()

def parse_weather(data: dict) -> pd.DataFrame:
    rows = []
    for ts in data["properties"]["timeseries"]:
        instant = ts["data"]["instant"]["details"]
        rows.append({
            "time": ts["time"],
            "temperature": instant.get("air_temperature"),
            "wind_speed": instant.get("wind_speed"),
            "precipitation": ts["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0),
            "symbol": ts["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", ""),
        })
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df

def save_weather(df: pd.DataFrame, label: str = "oslo"):
    path = Path("data/raw/met")
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"weather_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False)
    print(f"Lagret {len(df)} rader til {filename}")
    return filename