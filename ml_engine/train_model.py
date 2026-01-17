import pandas as pd
import numpy as np
import pickle
import os
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score, 
                             roc_auc_score, mean_absolute_error, mean_squared_error, 
                             confusion_matrix, roc_curve, auc)

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'scaler.pkl')
CSV_PATH = os.path.join(BASE_DIR, '..', 'sensor_data.csv') 
# --- 1. DATA LOADING ---
def load_data():
    # Check if CSV exists
    if os.path.exists('sensor_data.csv'):
        print(f"📂 Loading dataset from sensor_data.csv...")
        df = pd.read_csv('sensor_data.csv')
    elif os.path.exists(CSV_PATH):
        print(f"📂 Loading dataset from {CSV_PATH}...")
        df = pd.read_csv(CSV_PATH)
    else:
        print("❌ Error: 'sensor_data.csv' not found. Please upload the file.")
        return None

    # Ensure all required columns exist
    required_cols = ['methane', 'lpg', 'co', 'air_quality', 'flame_val', 'dht22_temp', 'humidity', 'status']
    if not all(col in df.columns for col in required_cols):
        print(f"❌ Error: CSV missing columns. Required: {required_cols}")
        return None

    # MAP STATUS to BINARY (Paper Logic: 1=Fire, 0=Safe/Warning)
    # We treat 'Warning' (2) as 0 for the Binary 'Fire Detector', 
    # but the Predictor.py logic will handle Warning based on probability.
    df['fire_label'] = df['status'].apply(lambda x: 1 if x == 1 else 0) 
    
    # Return 7 Features + Label
    return df[['methane', 'lpg', 'co', 'air_quality', 'flame_val', 'dht22_temp', 'humidity', 'fire_label']]

# --- 2. HDBMS SCORING (Equation 7) ---
def calculate_hdbms_score(y_true, y_pred, y_prob):
    # Weights from Paper
    w = {'acc': 0.167, 'prec': 0.167, 'rec': 0.25, 'f1': 0.25, 'auc': 0.083, 'mae': 0.042, 'rmse': 0.042}
    
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
    
    score = (w['acc']*acc) + (w['prec']*prec) + (w['rec']*rec) + (w['f1']*f1) + (w['auc']*auc_val) - (w['mae']*mae) - (w['rmse']*rmse)
    return score

# --- 3. PLOTTING FUNCTIONS ---
def plot_results(model, X_test, y_test, model_name):
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    # A. Confusion Matrix
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=['No Fire', 'Fire'], yticklabels=['No Fire', 'Fire'])
    plt.title(f'Confusion Matrix: {model_name}')
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.tight_layout()
    plt.savefig(os.path.join(BASE_DIR, 'confusion_matrix.png'))
    print("📊 Confusion Matrix saved to ml_engine/confusion_matrix.png")
    plt.close()

    # B. ROC Curve
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc = auc(fpr, tpr)
    
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (area = {roc_auc:.2f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title(f'ROC Curve: {model_name}')
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(os.path.join(BASE_DIR, 'roc_curve.png'))
    print("📈 ROC Curve saved to ml_engine/roc_curve.png")
    plt.close()

# --- 4. MAIN TRAINING LOOP ---
def train_and_select():
    df = load_data()
    if df is None: return

    X = df.drop('fire_label', axis=1)
    y = df['fire_label']
    
    # Split: 64% Train, 16% Val, 20% Test (Paper Config)
    X_train_full, X_test, y_train_full, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    X_train, X_val, y_train, y_val = train_test_split(X_train_full, y_train_full, test_size=0.2, random_state=42, stratify=y_train_full)
    
    # Scale Features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    
    # Define Models
    models = {
        "RandomForest": RandomForestClassifier(n_estimators=30, max_depth=10, min_samples_split=5, max_features='log2', random_state=42),
        "LogisticRegression": LogisticRegression(C=0.1, solver='liblinear', random_state=42),
        "SVC": SVC(C=1, degree=2, kernel='poly', probability=True, random_state=42),
        "DecisionTree": DecisionTreeClassifier(max_depth=4, min_samples_split=2, criterion='gini', random_state=42),
        "GradientBoosting": GradientBoostingClassifier(n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42)
    }
    
    best_score = -float('inf')
    best_name = ""
    best_obj = None
    
    print("\n--- HDBMS Selection Results (7 Features) ---")
    print(f"{'Model':<20} | {'Score (Si)':<12} | {'Accuracy':<10}")
    print("-" * 50)
    
    for name, clf in models.items():
        clf.fit(X_train_scaled, y_train)
        preds = clf.predict(X_val_scaled)
        probs = clf.predict_proba(X_val_scaled)[:, 1]
        
        score = calculate_hdbms_score(y_val, preds, probs)
        acc = accuracy_score(y_val, preds)
        
        print(f"{name:<20} | {score:.5f}      | {acc:.2%}")
        
        if score > best_score:
            best_score = score
            best_name = name
            best_obj = clf
            
    print("-" * 50)
    print(f" Winner: {best_name} with HDBMS Score: {best_score:.5f}")
    
    # Generate Plots for the Winner using Test Set
    plot_results(best_obj, X_test_scaled, y_test, best_name)

    # Final Retrain on Train+Val
    X_final_scaled = scaler.transform(X_train_full)
    best_obj.fit(X_final_scaled, y_train_full)
    
    # Save
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(best_obj, f)
    with open(SCALER_PATH, 'wb') as f:
        pickle.dump(scaler, f)
    print(f"✅ Best Model saved to {MODEL_PATH}")

if __name__ == "__main__":
    train_and_select()