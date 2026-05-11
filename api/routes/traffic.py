from fastapi import APIRouter
import asyncio
from api.services.vegvesen import fetch_all_points

router = APIRouter()

@router.get("/traffic")
async def get_traffic(days_back: int = 7):
    df = await fetch_all_points(days_back=days_back)
    return df.to_dict(orient="records")

@router.get("/points")
async def get_points():
    from api.services.vegvesen import fetch_oslo_points
    points = await fetch_oslo_points()
    return points