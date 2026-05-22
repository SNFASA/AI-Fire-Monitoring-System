import copy
import time

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (
    GridSearchCV,
    KFold,
    cross_val_score,
    learning_curve,
    train_test_split,
)
from sklearn.naive_bayes import GaussianNB
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

matplotlib.use("Agg")

data = pd.read_csv("cleaned_data.csv")

X = data[["smoke", "temperature", "humidity"]]
y = data["fire_label"]

selector = SelectKBest(score_func=mutual_info_classif, k="all")
selector.fit(X, y)
selected_features = X.columns[selector.get_support()]
X = X[selected_features]
print("Selected Features based on mutual information:", selected_features.tolist())

# Plot correlation matrix
sns.set_style("whitegrid")
plt.figure(figsize=(6, 5), dpi=1500)  # Smaller size with high resolution
correlation_matrix = pd.concat([X, y], axis=1).corr()
sns.heatmap(correlation_matrix, annot=True, cmap="coolwarm", fmt=".2f")
plt.savefig("correlation_matrix.png", bbox_inches="tight")
plt.close()

# Split into Train (64%), Validation (16%), and Test (20%)
X_temp, X_holdout, y_temp, y_holdout = train_test_split(
    X, y, test_size=0.2, random_state=42
)  # Hold-out set
X_train, X_val, y_train, y_val = train_test_split(
    X_temp, y_temp, test_size=0.2, random_state=42
)  # Train + validation split

print(
    f"Train size: {X_train.shape[0]}, Validation size: {X_val.shape[0]}, Holdout Test size: {X_holdout.shape[0]}"
)

# Detailed statistics of the datasets
print("Training data statistics:")
print(X_train.describe())
print("\nHoldout Test data statistics:")
print(X_holdout.describe())

# Class distribution
print("Training set class distribution:")
print(y_train.value_counts(normalize=True))

print("\nValidation set class distribution:")
print(y_val.value_counts(normalize=True))

print("\nHoldout Test set class distribution:")
print(y_holdout.value_counts(normalize=True))

models = {
    "RandomForest": RandomForestClassifier(
        n_estimators=100, max_features=0.5, random_state=42
    ),
    "LogisticRegression": LogisticRegression(max_iter=1000, random_state=42),
    "SVC": SVC(probability=True, random_state=42),
    "DecisionTree": DecisionTreeClassifier(random_state=42),
    "GaussianNB": GaussianNB(),
}

param_grids = {
    "RandomForest": {
        "n_estimators": [30],
        "max_depth": [10],
        "min_samples_split": [5],
        "min_samples_leaf": [5],
        "max_features": ["log2"],
    },
    "LogisticRegression": {
        "C": [0.1],  # Regularization strength
        "solver": ["liblinear"],
    },
    "SVC": {"C": [1], "degree": [2], "kernel": ["poly"]},
    "DecisionTree": {
        "max_depth": [4],
        "min_samples_split": [2],
        "min_samples_leaf": [2],
        "max_features": ["log2"],
        "criterion": ["gini"],
    },
    "GaussianNB": {"var_smoothing": [1e-7]},
}


# Function to perform GridSearchCV on each classifier
def optimize_model(model, param_grid, X_train, y_train):
    grid_search = GridSearchCV(
        estimator=model, param_grid=param_grid, cv=10, n_jobs=-1, verbose=0
    )
    grid_search.fit(X_train, y_train)
    print(f"Best Parameters for {model.__class__.__name__}: {grid_search.best_params_}")
    return grid_search.best_estimator_


# Function to plot learning curves
def plot_learning_curve(model, X, y, title):
    train_sizes, train_scores, test_scores = learning_curve(
        model,
        X,
        y,
        cv=10,
        n_jobs=-1,
        train_sizes=np.linspace(0.1, 1.0, 10),
        scoring="accuracy",
    )
    # Calculate the mean and standard deviation for training and test scores
    train_scores_mean = np.mean(train_scores, axis=1)
    test_scores_mean = np.mean(test_scores, axis=1)
    train_scores_std = np.std(train_scores, axis=1)
    test_scores_std = np.std(test_scores, axis=1)
    model_name = "Hybrid Dynamic Best Model"
    # Create the plot
    plt.figure(figsize=(8, 6), dpi=1500)
    plt.plot(train_sizes, train_scores_mean, "o-", color="r", label="Training Accuracy")
    plt.plot(
        train_sizes, test_scores_mean, "o-", color="g", label="Validation Accuracy"
    )
    # Plot the standard deviation as a shaded area
    plt.fill_between(
        train_sizes,
        train_scores_mean - train_scores_std,
        train_scores_mean + train_scores_std,
        color="r",
        alpha=0.1,
    )
    plt.fill_between(
        train_sizes,
        test_scores_mean - test_scores_std,
        test_scores_mean + test_scores_std,
        color="g",
        alpha=0.1,
    )
    plt.title(f"Learning Curve ({model_name})")
    plt.xlabel("Training Set Size")
    plt.ylabel("Accuracy")
    plt.legend(loc="best")
    plt.savefig(f"learning_curve_{model_name}.png", bbox_inches="tight")
    plt.close()


# Function to plot learning curves for the best model
def plot_learning_curve_best_model(best_model, X, y, title):
    train_sizes, train_scores, test_scores = learning_curve(
        best_model,
        X,
        y,
        cv=10,
        n_jobs=-1,
        train_sizes=np.linspace(0.1, 1.0, 10),
        scoring="accuracy",
    )

    # Calculate the mean and standard deviation for training and test scores
    train_scores_mean = np.mean(train_scores, axis=1)
    test_scores_mean = np.mean(test_scores, axis=1)
    train_scores_std = np.std(train_scores, axis=1)
    test_scores_std = np.std(test_scores, axis=1)
    model_name = "Hybrid Dynamic Best Model"
    # Create the plot
    plt.figure(figsize=(8, 6), dpi=1500)
    plt.plot(train_sizes, train_scores_mean, "o-", color="r", label="Training Accuracy")
    plt.plot(train_sizes, test_scores_mean, "o-", color="g", label="Testing Accuracy")
    # Plot the standard deviation as a shaded area
    plt.fill_between(
        train_sizes,
        train_scores_mean - train_scores_std,
        train_scores_mean + train_scores_std,
        color="r",
        alpha=0.1,
    )
    plt.fill_between(
        train_sizes,
        test_scores_mean - test_scores_std,
        test_scores_mean + test_scores_std,
        color="g",
        alpha=0.1,
    )
    # Adding labels and title
    plt.title(f"Learning Curve ({model_name})")
    plt.xlabel("Training Set Size", fontsize=12)
    plt.ylabel("Accuracy", fontsize=12)
    plt.legend(loc="best")
    plt.grid(True)
    plt.ylim(0, 1)
    plt.tight_layout()
    plt.savefig(f"learning_curve_best_model_{model_name}.png", bbox_inches="tight")
    plt.close()


# Function to add Gaussian noise to the dataset
def add_gaussian_noise(data, columns, mean=0, std_dev=10):
    noisy_data = data.copy()
    for column in columns:
        noise = np.random.normal(mean, std_dev, size=data[column].shape)
        noisy_data[column] = noisy_data[column] + noise
    return noisy_data


# Apply Gaussian noise to the data at different levels
perturbation_levels = [10, 20, 30]
perturbed_datasets = {}

for level in perturbation_levels:
    perturbed_data = add_gaussian_noise(
        data, ["smoke", "temperature", "humidity"], mean=0, std_dev=level
    )
    perturbed_datasets[level] = perturbed_data


# Function to evaluate model performance on noisy data
def evaluate_on_noisy_data(
    models, perturbed_datasets, X_train, X_test, y_train, y_test
):
    results = {}

    for level, perturbed_data in perturbed_datasets.items():
        # Split the perturbed data
        X_train_noisy = perturbed_data[["smoke", "temperature", "humidity"]].iloc[
            X_train.index
        ]
        X_test_noisy = perturbed_data[["smoke", "temperature", "humidity"]].iloc[
            X_test.index
        ]

        model_results = {}
        for name, model in models.items():
            # Fit the model on noisy data
            model.fit(X_train_noisy, y_train)
            y_pred = model.predict(X_test_noisy)

            # Calculate accuracy
            accuracy = accuracy_score(y_test, y_pred)
            model_results[name] = accuracy

        results[level] = model_results

    return results


# Evaluate models on the noisy datasets
results_with_noise = evaluate_on_noisy_data(
    models, perturbed_datasets, X_train, X_holdout, y_train, y_holdout
)
# Display the results
print("Robustness Analysis Results:")
for perturb_level, model_results in results_with_noise.items():
    print(f"\nPerturbation Level: ±{perturb_level}%")
    for model_name, accuracy in model_results.items():
        print(f"{model_name}: Accuracy = {accuracy:.4f}")


# Perform 10-fold cross-validation and evaluate models
def evaluate_models(X_train, X_val, X_test, y_train, y_val, y_test):
    results = {}
    kf = KFold(n_splits=10, shuffle=True, random_state=42)

    for name, model in models.items():
        optimized_model = optimize_model(model, param_grids[name], X_train, y_train)

        # Use validation set for performance during tuning
        cv_scores = cross_val_score(
            optimized_model, X_val, y_val, cv=kf, scoring="accuracy"
        )
        print(
            f"{name} Validation CV Accuracy: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}"
        )

        optimized_model.fit(pd.concat([X_train, X_val]), pd.concat([y_train, y_val]))
        y_pred = optimized_model.predict(X_test)
        y_pred_proba = (
            optimized_model.predict_proba(X_test)[:, 1]
            if hasattr(optimized_model, "predict_proba")
            else None
        )

        # Training accuracy
        y_train_full_pred = optimized_model.predict(pd.concat([X_train, X_val]))
        training_accuracy = accuracy_score(
            pd.concat([y_train, y_val]), y_train_full_pred
        )

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        roc_auc = (
            roc_auc_score(y_test, y_pred_proba) if y_pred_proba is not None else None
        )
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))

        results[name] = {
            "model": optimized_model,
            "cv_accuracy": np.mean(cv_scores),
            "cv_std": np.std(cv_scores),
            "training_accuracy": training_accuracy,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "roc_auc": roc_auc,
            "mae": mae,
            "rmse": rmse,
            "y_pred": y_pred,
            "y_pred_proba": y_pred_proba,
        }

        print(f"{name} metrics (on final hold-out set):")
        print(f"  Training Accuracy: {training_accuracy:.4f}")
        print(f"  Testing Accuracy: {accuracy:.4f}")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall: {recall:.4f}")
        print(f"  F1 Score: {f1:.4f}")
        if roc_auc is not None:
            print(f"  ROC AUC: {roc_auc:.4f}")
        print(f"  MAE: {mae:.4f}")
        print(f"  RMSE: {rmse:.4f}\n")

    return results


# Calculate scores for model selection
def calculate_scores(results):
    metrics = {
        "accuracy": 1,
        "precision": 1,
        "recall": 1,
        "f1": 1,
        "roc_auc": 1,
        "mae": -1,
        "rmse": -1,
    }

    weights = {
        "accuracy": 0.167,
        "precision": 0.167,
        "recall": 0.25,
        "f1": 0.25,
        "roc_auc": 0.083,
        "mae": 0.042,
        "rmse": 0.042,
    }

    scores = {}
    for name, result in results.items():
        score = 0
        for metric, direction in metrics.items():
            value = result[metric]
            if direction == 1:
                normalized_value = value
            else:
                normalized_value = 1 / (value + 1)
            score += weights[metric] * normalized_value
        scores[name] = score
    return scores


# Plot performance of each model
def plot_model_performance(results, X_test, y_test, best_model_name):
    plt.figure(figsize=(8, 5), dpi=1500)
    for name, result in results.items():
        y_pred_proba = result["y_pred_proba"]
        if y_pred_proba is not None:
            fpr, tpr, _ = roc_curve(y_test, y_pred_proba)
            label = f'{name} (AUC = {result["roc_auc"]:.3f})'
            if name == true_best_model_name:
                label = f'{best_model_name} (AUC = {result["roc_auc"]:.3f})'
                plt.plot(fpr, tpr, label=label, linewidth=3)
            else:
                plt.plot(fpr, tpr, label=label)
    plt.plot([0, 1], [0, 1], linestyle="--", color="gray")
    plt.xlabel("False Positive Rate", fontsize=12)
    plt.ylabel("True Positive Rate", fontsize=12)
    plt.legend(loc=(0.45, 0.15), fontsize=10)
    plt.grid(True)
    plt.savefig("roc_curve_comparison.png", bbox_inches="tight")
    plt.close()

    for name, result in results.items():
        model = result["model"]
        y_pred = result["y_pred"]

        # Confusion Matrix
        plt.figure(figsize=(6, 5), dpi=1500)
        conf_matrix = confusion_matrix(y_test, y_pred)
        sns.heatmap(
            conf_matrix,
            annot=True,
            fmt="d",
            cmap="Blues",
            cbar=False,
            annot_kws={"size": 14},
        )
        if name == true_best_model_name:
            title = f"{best_model_name}"
        else:
            title = f"{name}"
        plt.xlabel("Predicted", fontsize=12)
        plt.ylabel("Actual", fontsize=12)
        plt.title(title, fontsize=14)
        plt.savefig(f"confusion_matrix_{name}.png", bbox_inches="tight")
        plt.close()


def plot_precision_recall_curves(results, X_test, y_test, best_model_name):
    plt.figure(figsize=(8, 6), dpi=1500)

    for name, result in results.items():
        y_pred_proba = result["y_pred_proba"]
        if y_pred_proba is not None:
            precision, recall, _ = precision_recall_curve(y_test, y_pred_proba)
            avg_precision = average_precision_score(y_test, y_pred_proba)
            label = f"{name} (AP = {avg_precision:.3f})"
            avg_precision = average_precision_score(y_test, y_pred_proba)
            if name == true_best_model_name:
                label = f"{best_model_name} (AP = {avg_precision:.3f})"
                plt.plot(recall, precision, label=label, linewidth=3)
            else:
                plt.plot(recall, precision, label=label)

    plt.xlabel("Recall", fontsize=12)
    plt.ylabel("Precision", fontsize=12)
    plt.title("Precision-Recall Curves")
    plt.legend(loc="lower left")
    plt.grid(True)
    plt.savefig("precision_recall_curves.png", bbox_inches="tight")
    plt.close()


# plot for PR on noise values
def plot_pr_curve_10_percent_noise(
    models, perturbed_datasets, X_train, X_test, y_train, y_test, best_model_name
):
    level = 10
    perturbed_data = perturbed_datasets[level]
    X_train_noisy = perturbed_data[["smoke", "temperature", "humidity"]].iloc[
        X_train.index
    ]
    X_test_noisy = perturbed_data[["smoke", "temperature", "humidity"]].iloc[
        X_test.index
    ]

    plt.figure(figsize=(8, 6), dpi=1500)

    for name, model in models.items():
        model_copy = copy.deepcopy(model)
        model_copy.fit(X_train_noisy, y_train)

        if hasattr(model_copy, "predict_proba"):
            y_pred_proba = model_copy.predict_proba(X_test_noisy)[:, 1]
        elif hasattr(model_copy, "decision_function"):
            decision_scores = model_copy.decision_function(X_test_noisy)
            y_pred_proba = 1 / (1 + np.exp(-decision_scores))
        else:
            continue

        precision, recall, _ = precision_recall_curve(y_test, y_pred_proba)
        avg_precision = average_precision_score(y_test, y_pred_proba)

        if name == true_best_model_name:
            label = f"{best_model_name} (AP = {avg_precision:.3f})"
            plt.plot(recall, precision, label=label, linewidth=3)

        else:
            plt.plot(
                recall,
                precision,
                label=f"{name} (AP={avg_precision:.3f})",
                linewidth=1.5,
            )

    plt.title("Precision-Recall Curve at ±10% Gaussian Noise")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.legend(loc="lower left")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("precision_recall_curve_noisy_10.png", bbox_inches="tight")
    plt.close()


# Evaluate models on initial dataset
results = evaluate_models(X_train, X_val, X_holdout, y_train, y_val, y_holdout)
scores = calculate_scores(results)

# Select the best model initially
true_best_model_name = max(scores, key=scores.get)
best_model = results[true_best_model_name]["model"]
best_model_name = "Hybrid Dynamic Best Model"
print(f"Initial best model selected: {best_model_name}")

# Plot learning curves for the best model
plot_learning_curve(best_model, X_train, y_train, best_model_name)

# Plot learning curves for the best model
plot_learning_curve_best_model(best_model, X_train, y_train, best_model_name)

plot_precision_recall_curves(results, X_holdout, y_holdout, best_model_name)
# Plot PR curve on 10% noise
plot_pr_curve_10_percent_noise(
    models, perturbed_datasets, X_train, X_holdout, y_train, y_holdout, best_model_name
)


# Plot feature importance for the best model
def plot_feature_importance(model, feature_names):
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]

        # Individual Feature Importance
        plt.figure(figsize=(6, 4), dpi=1500)
        sns.barplot(
            x=importances[indices], y=np.array(feature_names)[indices], color="red"
        )
        plt.title("Individual Feature Importance", fontsize=14)
        plt.xlabel("Importance", fontsize=12)
        plt.ylabel("Feature", fontsize=12)
        plt.savefig("feature_importance_individual.png", bbox_inches="tight")
        plt.close()

        # Cumulative Feature Importance
        cumulative_importances = np.cumsum(importances[indices])
        plt.figure(figsize=(6, 4), dpi=1500)
        plt.plot(cumulative_importances, marker="o", color="red")
        plt.title("Cumulative Feature Importance", fontsize=14)
        plt.xlabel("Feature Index", fontsize=12)
        plt.ylabel("Cumulative Importance", fontsize=12)
        plt.grid(True)
        plt.savefig("feature_importance_cumulative.png", bbox_inches="tight")
        plt.close()


# Creating the 3D plot for Smoke vs Temperature vs Humidity
fig = plt.figure(figsize=(8, 5))
ax = fig.add_subplot(111, projection="3d")

# Plotting the 3D scatter plot
scatter = ax.scatter(
    data["smoke"],
    data["temperature"],
    data["humidity"],
    c=data["fire_label"],
    cmap="coolwarm",
    s=50,
    alpha=0.8,
)

# Adding labels
ax.set_xlabel("Smoke Levels")
ax.set_ylabel("Temperature (°C)")
ax.set_zlabel("Humidity (%)")

# Adding colorbar to represent fire labels (0: No Fire, 1: Fire)
cbar = fig.colorbar(scatter, ax=ax, pad=0.1)
cbar.set_label("Fire Label (0: No Fire, 1: Fire)")

# Save plot with 1500 DPI
plt.savefig("3d_plot_high_quality.png", dpi=1500)

plot_feature_importance(best_model, X.columns)

name_mapping = {
    "RandomForest": "RandomForest",
    "LogisticRegression": "Logistic Regression",
    "SVC": "SVC",
    "DecisionTree": "Decision Tree",
    "GaussianNB": "Gaussian NB",
}
name_mapping[true_best_model_name] = "Hybrid Dynamic \n Best Model"

# Plot metrics comparison as line chart
metrics_df = (
    pd.DataFrame(results)
    .T[["accuracy", "precision", "recall", "f1", "roc_auc", "mae", "rmse"]]
    .reset_index()
    .melt(id_vars="index")
)

# Rename the models in the 'index' column
metrics_df["index"] = metrics_df["index"].map(name_mapping)

plt.figure(figsize=(8, 5), dpi=1500)  # Smaller size with high resolution
sns.lineplot(data=metrics_df, x="index", y="value", hue="variable", marker="o")
plt.ylabel("Score", fontsize=12)
plt.xlabel("Models", fontsize=12)
plt.xticks(rotation=0)
plt.legend(loc=(0.77, 0.28), fontsize=10)
plt.grid(True)
plt.savefig("model_comparison.png", bbox_inches="tight")
plt.close()

# Plot initial performance of each model
plot_model_performance(results, X_holdout, y_holdout, best_model_name)


# Function to fetch the latest sensor data from ThingSpeak
def fetch_data():
    api_key = "J5TF4QOAPUQOV44R"
    sensor_channel_id = "2571096"

    url = f"https://api.thingspeak.com/channels/2571096/feeds/last.json?api_key=J5TF4QOAPUQOV44R"

    response = requests.get(url)
    data = response.json()

    try:
        temperature = float(data["field1"]) if data["field1"] is not None else None
        humidity = float(data["field2"]) if data["field2"] is not None else None
        smoke = float(data["field3"]) if data["field3"] is not None else None
    except (TypeError, ValueError) as e:
        print(f"Error converting data: {e}")
        return None

    if None in [temperature, humidity, smoke]:
        print("Invalid sensor data received, retrying...")
        return None

    # Return data in DataFrame with the correct column names
    return pd.DataFrame(
        [[smoke, temperature, humidity]], columns=["smoke", "temperature", "humidity"]
    )


# Function to send prediction result to ThingSpeak
def send_prediction(prediction):
    prediction_channel_id = "2571096"
    write_api_key = "MZ4SZ89H0GLFBZXO"

    url = f"https://api.thingspeak.com/update.json"
    data = {"api_key": write_api_key, "field4": prediction}
    response = requests.post(url, data=data)
    if response.status_code == 200:
        print("Prediction sent successfully")
    else:
        print("Failed to send prediction")


# Continuous loop to fetch data and make predictions
retrain_interval = 30
fetch_interval = 10

last_retrain_time = time.time()

try:
    while True:
        start_time = time.time()
        try:
            sensor_data = fetch_data()
            if sensor_data is None:
                time.sleep(fetch_interval)
                continue

            fire_prediction = best_model.predict(sensor_data)
            print("Fire Prediction:", "Yes" if fire_prediction[0] == 1 else "No")

            if hasattr(best_model, "predict_proba"):
                sensor_proba = best_model.predict_proba(sensor_data)[:, 1]
                print(f"Predicted fire probability: {sensor_proba[0]:.4f}")

            send_prediction(int(fire_prediction[0]))

            current_time = time.time()
            # Retrain if enough time has passed
            if current_time - last_retrain_time > retrain_interval:
                retrain_start = time.time()
                new_data = pd.read_csv("cleaned_data.csv")
                X = new_data[["smoke", "temperature", "humidity"]]
                y = new_data["fire_label"]
                X_temp, X_test, y_temp, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42
                )
                X_train, X_val, y_train, y_val = train_test_split(
                    X_temp, y_temp, test_size=0.2, random_state=42
                )

                results = evaluate_models(
                    X_train, X_val, X_test, y_train, y_val, y_test
                )
                scores = calculate_scores(results)
                true_best_model_name = max(scores, key=scores.get)
                best_model = results[true_best_model_name]["model"]
                best_model_name = "Hybrid Dynamic Best Model"
                print(f"Best model reselected: {best_model_name}")

                retrain_duration = time.time() - retrain_start
                print(f"Model retraining time: {retrain_duration:.2f} seconds")

                last_retrain_time = current_time

            latency = time.time() - start_time
            print(f"Selection loop latency: {latency:.3f} seconds")

            time.sleep(fetch_interval)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            time.sleep(fetch_interval)
except KeyboardInterrupt:
    print("Real-time fire detection stopped.")
