import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from api.services.vegvesen import fetch_all_points, save_raw

async def main():
    print("Henter trafikkdata fra Vegvesenet...")
    df = await fetch_all_points(days_back=7)

    if df.empty:
        print("Ingen data hentet.")
        return

    print(f"\nHentet totalt {len(df)} rader")
    print(df.head(10))
    save_raw(df)

asyncio.run(main())