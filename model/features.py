import pandas as pd
from pathlib import Path

def load_traffic() -> pd.DataFrame:
    path = Path("data/raw/vegvesen")
    files = sorted(path.glob("history_*.csv"))
    if not files:
        files = sorted(path.glob("traffic_*.csv"))
    if not files:
        raise FileNotFoundError("Ingen trafikkdata funnet.")
    print(f"Laster {len(files)} filer...")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["from"] = pd.to_datetime(df["from"], utc=True)
    print(f"Totalt {len(df)} rader lastet")
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
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
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
    ).astype(float).fillna(0).astype(int)
    return df

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_time_features(df)
    df = add_congestion_label(df)
    return df