import httpx
import asyncio
from datetime import datetime, timedelta, timezone

async def test():
    BASE_URL = "https://trafikkdata-api.atlas.vegvesen.no/"
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    query = """
    query {
      trafficData(trafficRegistrationPointId: "17684V2460285") {
        volume {
          byHour(
            from: "%s"
            to: "%s"
          ) {
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
    """ % (week_ago.isoformat(), now.isoformat())

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            BASE_URL,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        data = r.json()
        edges = data["data"]["trafficData"]["volume"]["byHour"]["edges"]
        print(f"Fikk {len(edges)} timer med data!")
        print(edges[0])

asyncio.run(test())