import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import httpx

router = APIRouter()

# Enkel TTL-cache: {key: (timestamp, verdi)}
_cache: dict = {}

def _cache_get(key: str, ttl: int):
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    return None

def _cache_set(key: str, value):
    _cache[key] = (time.time(), value)


@router.get("/points")
async def get_points():
    from api.services.vegvesen import fetch_oslo_points
    return await fetch_oslo_points()


@router.get("/weather")
async def get_weather():
    cached = _cache_get("weather", 600)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                "https://api.met.no/weatherapi/locationforecast/2.0/compact",
                params={"lat": 59.91, "lon": 10.75},
                headers={"User-Agent": "rushtime.no/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            _cache_set("weather", data)
            return data
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Tidsavbrudd mot MET API"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@router.get("/geocode")
async def geocode(q: str):
    if len(q) < 2:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q + " Oslo Norge",
                    "format": "json",
                    "limit": 6,
                    "addressdetails": 1,
                    "countrycodes": "no",
                },
                headers={
                    "User-Agent": "rushtime.no/1.0",
                    "Accept-Language": "no",
                    "Referer": "https://rushtime.no",
                },
            )
            if r.status_code == 200 and r.text.strip():
                return r.json()
        return []
    except httpx.TimeoutException:
        return []
    except Exception as e:
        print(f"Geocode feil: {e}")
        return []


@router.get("/reverse-geocode")
async def reverse_geocode(lat: float, lon: float):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
                headers={"User-Agent": "rushtime.no/1.0", "Accept-Language": "no"},
            )
            if r.status_code == 200:
                return r.json()
        return {}
    except Exception:
        return {}


@router.get("/route")
async def get_route(from_lon: float, from_lat: float, to_lon: float, to_lat: float):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://router.project-osrm.org/route/v1/driving/{from_lon},{from_lat};{to_lon},{to_lat}",
                params={"overview": "full", "geometries": "geojson"},
            )
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Tidsavbrudd mot OSRM"})
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

@router.get("/roads")
async def get_roads(south: float, west: float, north: float, east: float):
    cache_key = f"roads:{south:.2f},{west:.2f},{north:.2f},{east:.2f}"
    cached = _cache_get(cache_key, 300)
    if cached is not None:
        return cached

    query = (
        f'[out:json][timeout:25];'
        f'way["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        f'({south},{west},{north},{east});'
        f'out geom;'
    )
    async with httpx.AsyncClient(timeout=60) as client:
        for url in OVERPASS_ENDPOINTS:
            try:
                r = await client.post(url, data={"data": query})
                if r.status_code == 200 and r.text.strip():
                    data = r.json()
                    _cache_set(cache_key, data)
                    return data
                print(f"Overpass {url} svarte {r.status_code}")
            except httpx.TimeoutException:
                print(f"Roads: tidsavbrudd mot {url}")
            except Exception as e:
                print(f"Roads feil mot {url}: {e}")
    return {"elements": []}
