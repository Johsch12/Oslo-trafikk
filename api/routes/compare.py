from fastapi import APIRouter
from api.services.entur import fetch_transit_trip

router = APIRouter()

@router.get("/compare")
async def compare_transport(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    when: str
):
    transit = await fetch_transit_trip(from_lat, from_lon, to_lat, to_lon, when)
    return {"transit_options": transit}