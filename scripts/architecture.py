# scripts/architecture.py
from diagrams import Diagram
from diagrams.programming.language import Python

with Diagram("AI Fire Monitoring System", show=False):

    sensors = Python("Sensors")
    ml = Python("ML Engine")
    django = Python("Django Backend")
    database = Python("Database")

    sensors >> ml >> django >> database
