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