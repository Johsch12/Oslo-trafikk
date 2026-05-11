from pathlib import Path

files = {}

files["api/services/vegvesen.py"] = '''
import httpx
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://trafikkdata-api.atlas.vegvesen.no/"

POINTS_QUERY = """
{
  trafficRegistrationPoints(searchQuery: {
    roadCategoryIds: [E, R, F]
    countyNumbers: [3]
  }) {
    id
    name
    location {
      coordinates {
        latLon { lat lon }
      }
    }
  }
}
"""

async def fetch_oslo_points() -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": POINTS_QUERY},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
    points = data.get("data", {}).get("trafficRegistrationPoints", [])
    print(f"Fant {len(points)} malepunkter i Oslo")
    return points

async def fetch_traffic(point_id: str, from_time: datetime, to_time: datetime) -> list:
    query = """
    query {
      trafficData(trafficRegistrationPointId: "%s") {
        volume {
          byHour(from: "%s", to: "%s") {
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
    """ % (point_id, from_time.isoformat(), to_time.isoformat())

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

    edges = (
        data.get("data", {})
            .get("trafficData", {})
            .get("volume", {})
            .get("byHour", {})
            .get("edges", [])
    )
    rows = []
    for edge in edges:
        node = edge["node"]
        rows.append({
            "point_id": point_id,
            "from": node["from"],
            "to": node["to"],
            "volume": node["total"]["volumeNumbers"]["volume"],
            "coverage": node["total"]["coverage"]["percentage"],
        })
    return rows

async def fetch_all_points(days_back: int = 7) -> pd.DataFrame:
    points = await fetch_oslo_points()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(days=days_back)
    all_rows = []
    for point in points:
        point_id = point["id"]
        name = point["name"]
        lat = point["location"]["coordinates"]["latLon"]["lat"]
        lon = point["location"]["coordinates"]["latLon"]["lon"]
        try:
            rows = await fetch_traffic(point_id, from_time, to_time)
            for row in rows:
                row["name"] = name
                row["lat"] = lat
                row["lon"] = lon
            all_rows.extend(rows)
            print(f"Hentet {len(rows)} rader fra {name}")
        except Exception as e:
            print(f"Feil ved {name}: {e}")
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["from"] = pd.to_datetime(df["from"])
        df["to"] = pd.to_datetime(df["to"])
    return df

def save_raw(df: pd.DataFrame):
    path = Path("data/raw/vegvesen")
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"traffic_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False)
    print(f"Lagret {len(df)} rader til {filename}")
    return filename
'''.strip()

files["api/services/met.py"] = '''
import httpx
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
HEADERS = {"User-Agent": "oslo-trafikk/1.0 github.com/Johsch12/Oslo-trafikk"}

async def fetch_weather(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            BASE_URL,
            params={"lat": round(lat, 4), "lon": round(lon, 4)},
            headers=HEADERS
        )
        response.raise_for_status()
        return response.json()

def parse_weather(data: dict) -> pd.DataFrame:
    rows = []
    for ts in data["properties"]["timeseries"]:
        instant = ts["data"]["instant"]["details"]
        rows.append({
            "time": ts["time"],
            "temperature": instant.get("air_temperature"),
            "wind_speed": instant.get("wind_speed"),
            "precipitation": ts["data"].get("next_1_hours", {}).get("details", {}).get("precipitation_amount", 0),
            "symbol": ts["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", ""),
        })
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df

def save_weather(df: pd.DataFrame, label: str = "oslo"):
    path = Path("data/raw/met")
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"weather_{label}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False)
    print(f"Lagret {len(df)} rader til {filename}")
    return filename
'''.strip()

files["api/services/entur.py"] = '''
import httpx

BASE_URL = "https://api.entur.io/journey-planner/v3/graphql"
HEADERS = {
    "ET-Client-Name": "oslo-trafikk",
    "Content-Type": "application/json"
}

TRIP_QUERY = """
query Trip($from_lat: Float!, $from_lon: Float!, $to_lat: Float!, $to_lon: Float!, $when: DateTime!) {
  trip(
    from: { coordinates: { latitude: $from_lat, longitude: $from_lon } }
    to: { coordinates: { latitude: $to_lat, longitude: $to_lon } }
    dateTime: $when
    numTripPatterns: 3
  ) {
    tripPatterns {
      duration
      legs {
        mode
        line { publicCode }
        fromPlace { name }
        toPlace { name }
      }
    }
  }
}
"""

async def fetch_transit_trip(from_lat, from_lon, to_lat, to_lon, when: str) -> list:
    variables = {
        "from_lat": from_lat,
        "from_lon": from_lon,
        "to_lat": to_lat,
        "to_lon": to_lon,
        "when": when
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BASE_URL,
            json={"query": TRIP_QUERY, "variables": variables},
            headers=HEADERS
        )
        data = response.json()
    patterns = data.get("data", {}).get("trip", {}).get("tripPatterns", [])
    results = []
    for p in patterns:
        modes = [leg["mode"] for leg in p["legs"]]
        results.append({
            "duration_seconds": p["duration"],
            "duration_minutes": round(p["duration"] / 60),
            "modes": modes,
        })
    return results
'''.strip()

files["api/main.py"] = '''
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
'''.strip()

files["api/routes/traffic.py"] = '''
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
'''.strip()

files["api/routes/compare.py"] = '''
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
'''.strip()

files["model/features.py"] = '''
import pandas as pd
from pathlib import Path

def load_traffic() -> pd.DataFrame:
    path = Path("data/raw/vegvesen")
    files = sorted(path.glob("traffic_*.csv"))
    if not files:
        raise FileNotFoundError("Ingen trafikkdata funnet. Kjor fetch_historical.py forst.")
    df = pd.concat([pd.read_csv(f) for f in files])
    df["from"] = pd.to_datetime(df["from"], utc=True)
    return df

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hour"] = df["from"].dt.hour
    df["day_of_week"] = df["from"].dt.dayofweek   # 0=mandag, 6=sondag
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_rush_morning"] = df["hour"].between(7, 9).astype(int)
    df["is_rush_evening"] = df["hour"].between(15, 17).astype(int)
    df["month"] = df["from"].dt.month
    return df

def add_congestion_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Beregn gjennomsnitt per punkt
    mean_vol = df.groupby("point_id")["volume"].transform("mean")
    ratio = df["volume"] / (mean_vol + 1)
    df["congestion"] = pd.cut(
        ratio,
        bins=[0, 0.5, 1.0, 1.5, 2.0, 999],
        labels=["ingen", "lav", "moderat", "hoy", "svart"]
    )
    df["congestion_score"] = pd.cut(
        ratio,
        bins=[0, 0.5, 1.0, 1.5, 2.0, 999],
        labels=[0, 1, 2, 3, 4]
    ).astype(int)
    return df

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_time_features(df)
    df = add_congestion_label(df)
    return df
'''.strip()

files["model/train.py"] = '''
import pandas as pd
import pickle
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from model.features import load_traffic, build_features

def train():
    print("Laster data...")
    df = load_traffic()
    df = build_features(df)

    feature_cols = ["hour", "day_of_week", "is_weekend", "is_rush_morning", "is_rush_evening", "month", "volume"]
    X = df[feature_cols]
    y = df["congestion_score"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Trener modell...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    Path("model/saved").mkdir(exist_ok=True)
    with open("model/saved/model.pkl", "wb") as f:
        pickle.dump(model, f)
    print("Modell lagret til model/saved/model.pkl")

if __name__ == "__main__":
    train()
'''.strip()

files["model/predict.py"] = '''
import pickle
import pandas as pd
from pathlib import Path

LABELS = {0: "ingen", 1: "lav", 2: "moderat", 3: "hoy", 4: "svart"}
COLORS = {0: "#4CAF50", 1: "#8BC34A", 2: "#FFC107", 3: "#F44336", 4: "#7B1FA2"}

def load_model():
    with open("model/saved/model.pkl", "rb") as f:
        return pickle.load(f)

def predict(hour: int, day_of_week: int, volume: int = 200) -> dict:
    model = load_model()
    features = pd.DataFrame([{
        "hour": hour,
        "day_of_week": day_of_week,
        "is_weekend": int(day_of_week in [5, 6]),
        "is_rush_morning": int(7 <= hour <= 9),
        "is_rush_evening": int(15 <= hour <= 17),
        "month": 5,
        "volume": volume,
    }])
    score = model.predict(features)[0]
    return {
        "score": int(score),
        "label": LABELS[score],
        "color": COLORS[score],
    }

if __name__ == "__main__":
    for hour in [6, 8, 12, 17, 20]:
        result = predict(hour=hour, day_of_week=0)
        print(f"Kl {hour:02d}:00 mandag: {result}")
'''.strip()

files["model/evaluate.py"] = '''
import pickle
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from model.features import load_traffic, build_features

def evaluate():
    df = load_traffic()
    df = build_features(df)

    feature_cols = ["hour", "day_of_week", "is_weekend", "is_rush_morning", "is_rush_evening", "month", "volume"]
    X = df[feature_cols]
    y = df["congestion_score"]

    with open("model/saved/model.pkl", "rb") as f:
        model = pickle.load(f)

    y_pred = model.predict(X)
    print("Classification Report:")
    print(classification_report(y, y_pred))
    print("Confusion Matrix:")
    print(confusion_matrix(y, y_pred))

if __name__ == "__main__":
    evaluate()
'''.strip()

files["scripts/fetch_historical.py"] = '''
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from api.services.vegvesen import fetch_all_points, save_raw

async def main():
    print("Henter trafikkdata fra Vegvesenet...")
    df = await fetch_all_points(days_back=30)
    if df.empty:
        print("Ingen data hentet.")
        return
    print(f"Hentet totalt {len(df)} rader")
    print(df.head(10))
    save_raw(df)

asyncio.run(main())
'''.strip()

files["requirements.txt"] = '''
fastapi
uvicorn
httpx
pandas
numpy
scikit-learn
python-dotenv
pytest
'''.strip()

files["README.md"] = '''
# Oslo Trafikk

AI-drevet trafikkprediksjon for Oslo basert på data fra Statens Vegvesen og MET Norge.

## Funksjoner
- Kart over Oslo med fargelagte veier (gronn/gul/rod/lilla) basert på predikert ko
- Tidsslider for a se ko-prediksjon time for time
- Sammenligning av bil vs kollektivtransport
- Modell trent pa historiske trafikkdata + vaerdata

## Kom i gang

pip install -r requirements.txt
python scripts/fetch_historical.py
python model/train.py
uvicorn api.main:app --reload

## Datakilder
- Statens Vegvesen Trafikkdata API
- MET Norge Locationforecast API
- Entur Journey Planner API
'''.strip()

# Skriv alle filer
for path_str, content in files.items():
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"Skrev {path_str}")

print("\nAlle filer er klare!")