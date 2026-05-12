import pandas as pd
import lightgbm as lgb
import pickle
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from model.features import load_traffic, load_weather, build_features

def train():
    print("Laster data...")
    df = load_traffic()
    weather = load_weather()

    print("Bygger features...")
    df = build_features(df, weather)

    if weather is not None:
        feature_cols = [
            "hour", "day_of_week", "is_weekend", "is_rush_morning",
            "is_rush_evening", "month", "volume",
            "temperature", "precipitation", "wind_speed",
            "is_raining", "is_snowing", "is_windy"
        ]
    else:
        feature_cols = [
            "hour", "day_of_week", "is_weekend", "is_rush_morning",
            "is_rush_evening", "month", "volume"
        ]

    X = df[feature_cols]
    y = df["congestion_score"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Trener LightGBM med værfeatures...")
    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=63,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))

    Path("model/saved").mkdir(exist_ok=True)
    with open("model/saved/model.pkl", "wb") as f:
        pickle.dump(model, f)

    feature_importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)
    print("\nFeature importance:")
    print(feature_importance.to_string(index=False))

    print("\nModell lagret til model/saved/model.pkl")

if __name__ == "__main__":
    train()