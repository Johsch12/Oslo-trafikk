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