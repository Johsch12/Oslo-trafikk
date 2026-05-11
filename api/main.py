from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import traffic, compare

app = FastAPI(title="Oslo Trafikk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traffic.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")