import httpx

API_URL = "https://api.politiet.no/politiloggen/v1/messages"

async def fetch_oslo_incidents() -> list:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            API_URL,
            params={
                "Districts": "Oslo",
                "Categories": "Trafikk",
                "count": 50
            },
            headers={
                "User-Agent": "oslo-trafikk/1.0",
                "Accept": "application/json"
            }
        )
        print(f"Status: {response.status_code}")
        print(f"URL: {response.url}")
        if response.status_code != 200:
            print(response.text[:300])
            return []
        data = response.json()

    incidents = []
    messages = data if isinstance(data, list) else data.get("data", data.get("messages", []))
    for msg in messages:
        incidents.append({
            "title": msg.get("title", ""),
            "description": msg.get("body", msg.get("text", "")),
            "time": msg.get("created", msg.get("publishedOn", "")),
            "lat": msg.get("latitude") or msg.get("coordinates", {}).get("latitude") if msg.get("coordinates") else None,
            "lon": msg.get("longitude") or msg.get("coordinates", {}).get("longitude") if msg.get("coordinates") else None,
        })
    return incidents