# AI Fire Monitoring System 🛰️🔥

[![Django Ultimate CI](https://github.com/SNFASA/AI-Fire-Monitoring-System/actions/workflows/django-ci.yml/badge.svg)](https://github.com/SNFASA/AI-Fire-Monitoring-System/actions/workflows/django-ci.yml)
[![codecov](https://codecov.io/gh/SNFASA/AI-Fire-Monitoring-System/branch/main/graph/badge.svg)](https://codecov.io/gh/SNFASA/AI-Fire-Monitoring-System)
[![Maintainability](https://img.shields.io/badge/Maintainability-Radon%20A-brightgreen)](https://github.com/SNFASA/AI-Fire-Monitoring-System/actions)

[![Security: Bandit](https://img.shields.io/badge/Security-Bandit-yellow.svg)](https://github.com/SNFASA/AI-Fire-Monitoring-System/actions)
[![Dependency Audit](https://img.shields.io/badge/Dependencies-pip--audit-blue)](https://github.com/SNFASA/AI-Fire-Monitoring-System/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

----

An AI-powered IoT-based fire detection and monitoring system that provides real-time alerts, data analytics, and automated reporting to improve fire safety and emergency response efficiency.

🚀 Overview

The AI Fire Monitoring System integrates IoT sensors and machine learning algorithms to detect heat, gas, smoke, humidity, air quality and using satellite capture image for detect forest fire in real time. Once a potential fire is identified, the system instantly sends alerts to relevant authorities such as BOMBA JBPM officers, enabling faster response and reducing the risk of major damage.

🧠 Key Features

🔍 AI Detection: Uses computer vision and sensor data for accurate fire identification

🌐 IoT Integration: Connects multiple monitoring devices through a centralized network

📊 Real-Time Dashboard: Displays live status, fire locations, and historical data

📱 Automated Alerts: Sends notifications via mobile and web platforms

🧾 Reporting Module: Generates analytical reports for post-incident review

☁️ Cloud Storage: Stores sensor data and event logs securely

⚙️ Tech Stack

Frontend: Web (Django templates or SPA frontend)
Backend: Python (Django)
Database: PostgreSQL (manage with pgAdmin)
AI & ML: (see `ml_engine` for model code)

IoT Hardware: ESP32, Flame Sensor, Smoke Sensor, DHT11 (Temperature)

## 📦 Installation

### Prerequisites

Before installing the AI Fire Monitoring System, ensure you have the following installed:

- **Python 3.8+** – [Download Python](https://www.python.org/downloads/)
- **Git** – [Download Git](https://git-scm.com/)
- **PostgreSQL** – [Download PostgreSQL](https://www.postgresql.org/download/)
- **pgAdmin** (optional, for DB management) – [pgAdmin](https://www.pgadmin.org/)
- **Node.js & npm** (optional, only if you run a separate SPA frontend)

### Backend Setup (Django)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SNFASA/AI-Fire-Monitoring-System.git
   cd AI-Fire-Monitoring-System
   ```

2. **Create a virtual environment and activate it:**
   ```bash
   python -m venv .venv
   # On Windows (PowerShell): .venv\Scripts\Activate.ps1
   # On Windows (cmd): .venv\Scripts\activate
   # On macOS / Linux: source .venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   - Create a `.env` file in the project root (the project reads env vars via settings)
   - Add PostgreSQL connection info and Django secret
   ```env
   SECRET_KEY=your_secret_key
   POSTGRES_DB=your_db_name
   POSTGRES_USER=your_db_user
   POSTGRES_PASSWORD=your_db_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   # Or provide a single DATABASE_URL, e.g.:
   # DATABASE_URL=postgres://user:pass@localhost:5432/dbname
   ```

   You can manage the database with `pgAdmin` or `psql`.

5. **Create the PostgreSQL database (example using psql):**
   ```bash
   createdb -U your_db_user your_db_name
   ```

6. **Run database migrations and create a superuser:**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

7. **Start the backend server (development):**
   ```bash
   python manage.py runserver
   ```

### Frontend (Web)

This project includes a Django-based web frontend (templates). If you use a separate SPA (React/Vue/Angular), run its setup in the `frontend/` folder if present:

1. **Install frontend dependencies (optional SPA):**
   ```bash
   npm install
   npm run build    # or: npm start for dev
   ```

2. **Serve static files** (Django): ensure `STATIC_ROOT` is configured and run `collectstatic` for production.

### Common Commands

- **Run tests:**
  ```bash
  pytest
  ```

- **Start IoT simulator:**
  ```bash
  python simulator.py
  ```

- **Check dependencies:**
  ```bash
  pip-audit
  ```

## 🎯 How to Use

### Starting the System

1. **Launch the backend server:**
   ```bash
   python manage.py runserver
   ```
   The API will be available at `http://localhost:8000`

2. **Start the mobile app:**
   ```bash
   flutter run
   ```

### Key Features Guide

#### 🔍 **Fire Detection Dashboard**
- Open the app and navigate to the Dashboard
- View real-time sensor data from connected IoT devices
- Monitor temperature, humidity, smoke levels, and air quality
- Visual indicators show fire risk status (Green/Yellow/Red)

#### 🚨 **Receiving Alerts**
- Enable notifications in app settings
- Alerts are triggered automatically when fire is detected
- Tap on alert to view detailed information and location
- Share alerts with emergency contacts

#### 📊 **Viewing Analytics**
- Navigate to the Analytics section
- View historical fire incident reports
- Generate custom reports by date range
- Export data for analysis in CSV format

#### 🗺️ **Satellite Image Monitoring**
- Use the Map view to see satellite-captured fire locations
- Zoom in for detailed area monitoring
- Track multiple fire incidents simultaneously
- View weather conditions affecting fire spread

#### ⚙️ **Configuration**
- Go to Settings to configure:
  - Alert preferences and notification channels
  - Sensor sensitivity thresholds
  - Connected IoT devices management
  - Emergency contact information

### Common Commands

- **Run tests:**
  ```bash
  pytest
  ```

- **Run linting:**
  ```bash
  python -m pylint src/
  ```

- **Start IoT simulator:**
  ```bash
  python simulator.py
  ```

- **Check dependencies:**
  ```bash
  pip-audit
  ```

🔄 Development Methodology

This project follows the Agile methodology, allowing iterative development across six main phases:

Planning – Define project scope, goals, and risk assessment

Analysis – Gather and document system requirements

Design – Develop architecture, database, and UI prototypes

Implementation – Code system modules and integrate AI models

Testing – Perform functional, performance, and user acceptance tests

Deployment – Deploy to live servers and train users

📅 Project Timeline

Duration: Oct 6, 2025 – Jul 6, 2026

Method: Agile with 2-week sprints (≈18 sprints)

Platforms: Android & iOS

Phases Overlap: Designed for continuous iteration and improvement

🤝 Contributors

Project Leader: [SNFASE]

Supervisor: [Dr. MOHD ZANES BIN SAHID]

Institution: Universiti Tun Hussein Onn Malaysia (UTHM)
---

📫 Contact

For inquiries or collaboration:
📧 [ai230046@student.uthm.edu.my]
🌍 [https://www.linkedin.com/in/syed-nabil-b266341bb/]
