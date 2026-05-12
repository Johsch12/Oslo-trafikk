import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from api.services.politiet import fetch_oslo_incidents

async def main():
    print("Henter hendelser fra politiloggen...")
    incidents = await fetch_oslo_incidents()
    print(f"Fant {len(incidents)} trafikkhendelser i Oslo\n")
    for i in incidents[:5]:
        print(f"- {i['time']}")
        print(f"  {i['title']}")
        print(f"  {i['description'][:100]}\n")

asyncio.run(main())