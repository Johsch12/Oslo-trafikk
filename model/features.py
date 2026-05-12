import pandas as pd
from pathlib import Path

def load_traffic() -> pd.DataFrame:
    path = Path("data/raw/vegvesen")
    files = sorted(path.glob("history_*.csv"))
    if not files:
        files = sorted(path.glob("traffic_*.csv"))
    if not files:
        raise FileNotFoundError("Ingen trafikkdata funnet.")
    print(f"Laster {len(files)} trafikkfiler...")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["from"] = pd.to_datetime(df["from"], utc=True)
    print(f"Totalt {len(df)} trafikkrader")
    return df

def load_weather() -> pd.DataFrame:
    path = Path("data/raw/met/weather_blindern_2015_2026.csv")
    if not path.exists():
        print("Ingen værdata funnet, hopper over")
        return None
    print("Laster værdata...")
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates(subset="time").sort_values("time")
    print(f"Totalt {len(df)} værobservasjoner")
    return df

def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["hour"] = df["from"].dt.hour
    df["day_of_week"] = df["from"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_rush_morning"] = df["hour"].between(7, 9).astype(int)
    df["is_rush_evening"] = df["hour"].between(15, 17).astype(int)
    df["month"] = df["from"].dt.month
    return df

def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    weather = weather.rename(columns={"time": "from"})
    df = pd.merge_asof(
        df.sort_values("from"),
        weather[["from", "temperature", "precipitation", "wind_speed"]].sort_values("from"),
        on="from",
        tolerance=pd.Timedelta("1h"),
        direction="nearest"
    )
    df["temperature"] = df["temperature"].fillna(10.0)
    df["precipitation"] = df["precipitation"].fillna(0.0)
    df["wind_speed"] = df["wind_speed"].fillna(2.0)
    df["is_raining"] = (df["precipitation"] > 0.5).astype(int)
    df["is_snowing"] = ((df["precipitation"] > 0.5) & (df["temperature"] < 1.0)).astype(int)
    df["is_windy"] = (df["wind_speed"] > 8.0).astype(int)
    return df

def add_congestion_label(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    mean_vol = df.groupby("point_id")["volume"].transform("mean")
    ratio = df["volume"] / (mean_vol + 1)
    df["congestion_score"] = pd.cut(
        ratio,
        bins=[0, 0.5, 1.0, 1.5, 2.0, 999],
        labels=[0, 1, 2, 3, 4]
    ).astype(float).fillna(0).astype(int)
    return df

def build_features(df: pd.DataFrame, weather: pd.DataFrame = None) -> pd.DataFrame:
    df = add_time_features(df)
    df = add_congestion_label(df)
    if weather is not None:
        df = add_weather_features(df, weather)
    return df