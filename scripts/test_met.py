import httpx
import asyncio

async def test():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    params = {"lat": 59.91, "lon": 10.75}
    headers = {"User-Agent": "oslo-trafikk/1.0 github.com/Johsch12/Oslo-trafikk"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params, headers=headers)
        print(f"Status: {r.status_code}")
        data = r.json()
        ts = data["properties"]["timeseries"]
        print(f"Fikk {len(ts)} tidspunkter\n")
        for t in ts[:5]:
            details = t["data"]["instant"]["details"]
            print(f"{t['time']}")
            print(f"  Temperatur: {details['air_temperature']}°C")
            print(f"  Vind: {details['wind_speed']} m/s")
            precip = t["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0)
            print(f"  Nedbør: {precip} mm")

asyncio.run(test())