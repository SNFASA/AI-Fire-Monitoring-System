import pandas as pd
import numpy as np
import pickle 
import os
import matplotlib.pyplot as plt
import seaborn as sns 
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, roc_auc_score, auc, roc_curve
from sklearn.preprocessing import label_binarize

#ml model
from sklearn.svm import SVC
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier,VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

# dataset 
csv_path = 'sensor_data.csv'
if not os.path.exists(csv_path):
     print(f"Dataset not found at {csv_path}. Please generate the dataset first.")
     exit(1)

print("Loading dataset...")
df = pd.read_csv(csv_path)
print(f"Dataset loaded with {len(df)} rows.")
print(df['status'].value_counts())

# Features and target
X = df.drop('status', axis=1)
y = df['status']

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.8, random_state=42, stratify=y)
print(f"Training samples: {len(X_train)}, Testing samples: {len(X_test)}")

# Model with high sensitivity 
clf1 = LogisticRegression(class_weight='balanced', max_iter=60000, random_state=42)
clf2= DecisionTreeClassifier(class_weight='balanced', random_state=42)
clf3 = RandomForestClassifier(class_weight='balanced', n_estimators=100, random_state=42)
clf4 = SVC(class_weight='balanced', probability=True, random_state=42, kernel='rbf')
clf5 = GradientBoostingClassifier(n_estimators=100, random_state=42, learning_rate=0.1)

#voting 
voting_model = VotingClassifier(
    estimators=[
        ('lr', clf1),
        ('dt', clf2),
        ('rf', clf3),
        ('svc', clf4),
        ('gb', clf5)
    ],
    voting='soft'
)
print("Training ensemble model...")
voting_model.fit(X_train, y_train)

preds = voting_model.predict(X_test)
accuracy = accuracy_score(y_test, preds)
print(f"Ensemble Model Accuracy: {accuracy*100:.2f}%")

# Generate Graphs 
if not os.path.exists('ml_engine'):
    os.makedirs('ml_engine')
    
# confusion matrix
print("Generating confusion matrix...")
conf_matrix =confusion_matrix(y_test, preds)
print(classification_report(y_test, preds, target_names=['Safe', 'Fire', 'Gas Leak']))

plt.figure(figsize=(8,6))
sns.heatmap(
    conf_matrix,
    annot=True,
    fmt='d',
    cmap='Blues',
    xticklabels=['Safe', 'Fire', 'Gas Leak'],
    yticklabels=['Safe', 'Fire', 'Gas Leak']
    )

plt.xlabel('Predicted Label')
plt.ylabel('Actual')
plt.title('Confusion Matrix (High Sensitivity Model)')
plt.savefig('ml_engine/confusion_matrix2.png')
print("Confusion matrix saved to ml_engine/confusion_matrix2.png")

# ROC Curve Generation
print("\nGenerating ROC AUC scores...")
y_test_bin = label_binarize(y_test, classes=[0, 1, 2])
n_classes = y_test_bin.shape[1]
y_score = voting_model.predict_proba(X_test)
plt.figure(figsize=(10, 8))
fpr = dict()
tpr = dict()
roc_auc = dict()
colors = ['blue', 'red', 'orange']
class_names = ['Safe', 'Fire', 'Gas Leak']

for i, color in zip(range(n_classes), colors):
    fpr[i], tpr[i], _ = roc_curve(y_test_bin[:, i], y_score[:, i])
    roc_auc[i] = auc(fpr[i], tpr[i])
    plt.plot(fpr[i], tpr[i], color=color, lw=2,
             label=f'ROC curve of {class_names[i]} (area = {roc_auc[i]:.2f})')


plt.plot([0, 1], [0, 1], 'k--', lw=2) 
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Analysis (Multi-Class)')
plt.legend(loc="lower right")

# 5. Save
plt.savefig('ml_engine/roc_curve2.png')
print("✅ Saved ml_engine/roc_curve2.png")

# Save the trained model
print("Saving trained model...")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, 'fire_model.pkl')
with open(MODEL_PATH, 'wb') as f:
    pickle.dump(voting_model, f)

print(f"\nDONE! High-Sensitivity Model saved to: {MODEL_PATH}")