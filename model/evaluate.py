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