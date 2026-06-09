# FLOPs Analysis and Optimization in Fire Detection Machine Learning System

## 1. Introduction
In this project, an ensemble machine learning model is used to classify fire-related conditions into three classes: **Safe**, **Fire**, and **Warning (gas leak)**.  
The model is trained using sensor data collected from multiple environmental sensors.

This document explains:
- What FLOPs are
- Whether FLOPs can be changed
- How FLOPs were reduced in this system
- The impact on performance

---

## 2. What Are FLOPs?
**FLOPs (Floating Point Operations)** represent the number of mathematical computations (such as addition and multiplication) performed during model training or inference.

Important clarification:
- FLOPs measure **computational cost**
- FLOPs are **not learned from data**
- FLOPs depend on model design and parameters

---

## 3. Dataset and System Configuration

### 3.1 Dataset
- Number of samples: **90,050**
- Number of features: **7**
- Number of classes: **3**

### 3.2 Hardware Used
- Processor: **AMD Ryzen 5 7535HS (6 cores, 12 threads)**
- RAM: **16 GB**
- Operating System: **64-bit**
- Training framework: **scikit-learn (CPU-based)**

---

## 4. Original Model Configuration

The ensemble model consists of five classifiers:

| Model | Key Parameters |
|------|---------------|
| Logistic Regression | max_iter = 60,000 |
| Decision Tree | default |
| Random Forest | 100 trees |
| Support Vector Machine | RBF kernel |
| Gradient Boosting | 100 estimators |

The models are combined using a **soft voting classifier**.

---

## 5. Estimated FLOPs (Before Optimization)

| Model | Approximate FLOPs |
|-----|------------------|
| Logistic Regression | ~37.8 billion |
| Decision Tree | ~0.01 billion |
| Random Forest (100 trees) | ~1.04 billion |
| SVM (RBF kernel) | ~56.8 billion |
| Gradient Boosting (100 estimators) | ~1.04 billion |

### Total Training FLOPs:
**≈ 100 billion FLOPs**

---

## 6. Can FLOPs Be Changed?
Yes. FLOPs are **not fixed** and can be changed by modifying:
- Model choice
- Hyperparameters
- Dataset size
- Number of features

---

## 7. FLOPs Optimization Strategies Applied

### 7.1 Reduce Logistic Regression Iterations
```python
LogisticRegression(max_iter=3000)
