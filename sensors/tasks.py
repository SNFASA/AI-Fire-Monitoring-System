import logging

from celery import shared_task

from .services import fetch_and_filter_hotspots

logger = logging.getLogger(__name__)

import os
import pickle

import numpy as np
import pandas as pd
from django.conf import settings

# Scikit-learn imports
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from sensors.models import SensorDataLog

# Ensure paths align with your Django project structure
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fire_model.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
CSV_PATH = os.path.join(BASE_DIR, "cleaned_data.csv")

@shared_task(name="your_fire_app.tasks.update_malaysia_hotspots")
def update_malaysia_hotspots():
    logger.info(
        "⏰ [Celery] Triggering scheduled 2-hour NASA FIRMS hotspot synchronization..."
    )
    try:
        result = fetch_and_filter_hotspots()
        logger.info(f"✅ [Celery] Synchronization result: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ [Celery] Critical failure in background sync task: {str(e)}")
        return f"Failed due to error: {str(e)}"


def calculate_hdbms_score(y_true, y_pred, y_prob):
    """Equation 7 from the research paper."""
    w = {
        "acc": 0.167,
        "prec": 0.167,
        "rec": 0.25,
        "f1": 0.25,
        "auc": 0.083,
        "mae": 0.042,
        "rmse": 0.042,
    }

    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred)

    try:
        auc_val = roc_auc_score(y_true, y_prob)
    except:
        auc_val = 0.5

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    score = (
        (w["acc"] * acc)
        + (w["prec"] * prec)
        + (w["rec"] * rec)
        + (w["f1"] * f1)
        + (w["auc"] * auc_val)
        - (w["mae"] * mae)
        - (w["rmse"] * rmse)
    )
    return score


def run_hdbms_training_task():
    print("🔄 [Django Q] Starting Automated HDBMS Training from Live DB logs...")

    # 1. Pull data directly from the live Django Database
    logs = SensorDataLog.objects.all().values(
        "methane",
        "lpg",
        "co",
        "air_quality",
        "flame_val",
        "dht22_temp",
        "humidity",
        "status",
    )

    if not logs.exists() or logs.count() < 100:
        print(
            f"⚠️ [Django Q] Not enough data logs yet ({logs.count()}/100 minimum). Skipping training."
        )
        return False

    # 2. Convert Django QuerySet into a Pandas DataFrame instantly
    df = pd.DataFrame(list(logs))

    # 3. Map the text 'status' column into a binary 'fire_label' (Paper Logic)
    # 1 if it was a real verified fire, 0 if it was Safe or a minor Gas Warning
    df["fire_label"] = df["status"].apply(lambda x: 1 if x == "Fire" else 0)

    # Clean up features and target
    X = df[
        ["methane", "lpg", "co", "air_quality", "flame_val", "dht22_temp", "humidity"]
    ]
    y = df["fire_label"]

    # Split data: 64% Train, 16% Val, 20% Test
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y if len(np.unique(y)) > 1 else None,
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full,
        y_train_full,
        test_size=0.2,
        random_state=42,
        stratify=y_train_full if len(np.unique(y_train_full)) > 1 else None,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    # Define the 5 specific classifiers
    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=30,
            max_depth=10,
            min_samples_split=5,
            max_features="log2",
            random_state=42,
        ),
        "LogisticRegression": LogisticRegression(
            C=0.1, solver="liblinear", random_state=42
        ),
        "SVC": SVC(C=1, degree=2, kernel="poly", probability=True, random_state=42),
        "DecisionTree": DecisionTreeClassifier(
            max_depth=4, min_samples_split=2, criterion="gini", random_state=42
        ),
        "GaussianNB": GaussianNB(),
    }

    best_score = -float("inf")
    best_name = ""
    best_obj = None

    for name, clf in models.items():
        clf.fit(X_train_scaled, y_train)
        preds = clf.predict(X_val_scaled)
        probs = clf.predict_proba(X_val_scaled)[:, 1]

        score = calculate_hdbms_score(y_val, preds, probs)  # Uses formula from paper

        if score > best_score:
            best_score = score
            best_name = name
            best_obj = clf

    print(f"✅ [Django Q] HDBMS Winner: {best_name} (Score: {best_score:.5f})")

    # Final training on entire Train+Val history
    X_final_scaled = scaler.transform(X_train_full)
    best_obj.fit(X_final_scaled, y_train_full)

    # Overwrite production files smoothly
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(best_obj, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    print(f"🚀 [Django Q] Production AI updated smoothly to use historical logs.")
    return True
