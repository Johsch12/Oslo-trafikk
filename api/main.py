from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api.routes import traffic, compare


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await traffic._http.aclose()


app = FastAPI(title="Oslo Trafikk API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".js", ".html", ".css")) or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(traffic.router, prefix="/api")
app.include_router(compare.router, prefix="/api")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
