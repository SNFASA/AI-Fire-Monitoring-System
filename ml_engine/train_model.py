import pandas as pd
import numpy as np
import pickle
import os
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report, roc_curve, auc
from sklearn.preprocessing import label_binarize

# IMPORT 5 MODELS FOR VOTING
from sklearn.svm import SVC
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression

# ==========================================
# 1. GENERATE SYNTHETIC DATA
# ==========================================
rng = np.random.default_rng(seed=42)
data_size = 90000

# Sensors (12-bit ADC: 0-4095)
methane = rng.integers(200, 4096, size=data_size)      # MQ-4
lpg = rng.integers(200, 4096, size=data_size)          # MQ-5
co = rng.integers(100, 4096, size=data_size)           # MQ-7
air_quality = rng.integers(300, 4096, size=data_size)  # MQ-135
flame_val = rng.integers(0, 4096, size=data_size)      # Flame
dht22_temp = rng.integers(15, 90, size=data_size)      # Temp
humidity = rng.integers(10, 90, size=data_size)        # Humidity

df = pd.DataFrame({
    'methane': methane,
    'lpg': lpg,
    'co': co,
    'air_quality': air_quality,
    'flame_val': flame_val,
    'dht22_temp': dht22_temp,
    'humidity': humidity
})

# ==========================================
# 2. DEFINE RULES (TEACHING)
# ==========================================
def teach_the_ai(row):
    # Rule 1: Fire (Low Flame OR High Temp+Smoke)
    if (row['flame_val'] < 600) or (row['dht22_temp'] > 55 and row['air_quality'] > 1800):
        return 1
    # Rule 2: Gas Leak
    if (row['methane'] > 2500) or (row['lpg'] > 2500) or (row['co'] > 2500):
        return 2
    return 0

df['status'] = df.apply(teach_the_ai, axis=1)

# ==========================================
# 3. TRAIN THE MODEL
# ==========================================
X = df.drop('status', axis=1)
y = df['status']

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Initialize Models (Explicit params to fix SonarLint warnings)
clf1 = LogisticRegression(max_iter=60000, random_state=42)
clf2 = DecisionTreeClassifier(ccp_alpha=0.0, random_state=42)
clf3 = RandomForestClassifier(n_estimators=100, min_samples_leaf=1, max_features='sqrt', random_state=42)
clf4 = SVC(probability=True, kernel='rbf', C=1.0, gamma='scale', random_state=42)
clf5 = GradientBoostingClassifier(learning_rate=0.1, n_estimators=100, random_state=42)

# Create Voting Committee
# CHANGED: 'soft' voting is required for ROC Curves and probability scores
voting_model = VotingClassifier(
    estimators=[('lr', clf1), ('dt', clf2), ('rf', clf3), ('svm', clf4), ('gb', clf5)],
    voting='soft'
)

print("Training the 5-Model Ensemble (Soft Voting)...")
voting_model.fit(X_train, y_train)

# Check Accuracy
preds = voting_model.predict(X_test)
acc_score = accuracy_score(y_test, preds)
print(f"Accuracy: {acc_score * 100:.2f}%")

# ==========================================
# 4. GENERATE VISUALIZATIONS
# ==========================================

# A. Confusion Matrix
print("\n--- Generating Confusion Matrix ---")
conf_matrix = confusion_matrix(y_test, preds)
print(classification_report(y_test, preds, target_names=['Safe', 'Fire', 'Gas Leak']))

plt.figure(figsize=(8, 6))
sns.heatmap(conf_matrix, annot=True, fmt='d', cmap='Blues', 
            xticklabels=['Safe', 'Fire', 'Gas'], 
            yticklabels=['Safe', 'Fire', 'Gas'])
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.title('Confusion Matrix')
plt.savefig('ml_engine/confusion_matrix.png') # Save first
# plt.show() # Uncomment this if you want a popup window
print("✅ Saved ml_engine/confusion_matrix.png")

# B. ROC Curve
print("\n--- Generating ROC Curve ---")
y_test_bin = label_binarize(y_test, classes=[0, 1, 2])
n_classes = y_test_bin.shape[1]
y_score = voting_model.predict_proba(X_test)

fpr = dict()
tpr = dict()
roc_auc = dict()

for i in range(n_classes):
    fpr[i], tpr[i], _ = roc_curve(y_test_bin[:, i], y_score[:, i])
    roc_auc[i] = auc(fpr[i], tpr[i])

plt.figure(figsize=(10, 8))
colors = ['blue', 'red', 'orange']
class_names = ['Safe', 'Fire', 'Gas Leak']

for i, color in zip(range(n_classes), colors):
    plt.plot(fpr[i], tpr[i], color=color, lw=2,
             label='ROC curve of {0} (area = {1:0.2f})'.format(class_names[i], roc_auc[i]))

plt.plot([0, 1], [0, 1], 'k--', lw=2)
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Analysis (Multi-Class)')
plt.legend(loc="lower right")
plt.savefig('ml_engine/roc_curve.png') # Save first
# plt.show() # Uncomment this if you want a popup window
print("✅ Saved ml_engine/roc_curve.png")

# ==========================================
# 5. SAVE THE BRAIN (.pkl)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')

with open(MODEL_PATH, 'wb') as f:
    pickle.dump(voting_model, f)

print(f"\nDONE! Model saved to: {MODEL_PATH}")