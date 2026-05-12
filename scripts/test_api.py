import httpx
import asyncio

POINTS = [
    ("17684V2460285", "Dr. Eufemias gate"),
    ("97411V72812", "E6 Ryen"),
    ("44656V72812", "Gammel test-ID"),
]

async def test_point(point_id, name):
    query = """
    query {
      trafficData(trafficRegistrationPointId: "%s") {
        volume {
          byHour(
            from: "2015-01-01T00:00:00+00:00"
            to: "2015-01-05T00:00:00+00:00"
          ) {
            edges {
              node { from }
            }
          }
        }
      }
    }
    """ % point_id

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://trafikkdata-api.atlas.vegvesen.no/",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        data = r.json()
        try:
            edges = data["data"]["trafficData"]["volume"]["byHour"]["edges"]
            print(f"{name}: {len(edges)} timer fra 2015")
            if edges:
                print(f"  Forste: {edges[0]['node']['from']}")
        except:
            print(f"{name}: ingen data eller feil")

async def main():
    # Hent alle Oslo-punkter og test de første 10
    query = """
    {
      trafficRegistrationPoints(searchQuery: {
        roadCategoryIds: [E, R, F]
        countyNumbers: [3]
      }) {
        id
        name
      }
    }
    """
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://trafikkdata-api.atlas.vegvesen.no/",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        points = r.json()["data"]["trafficRegistrationPoints"]

    print(f"Tester {len(points[:15])} punkter...")
    for p in points[:15]:
        await test_point(p["id"], p["name"])

asyncio.run(main())