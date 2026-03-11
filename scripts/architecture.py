# scripts/architecture.py
from diagrams import Diagram
from diagrams.programming.language import Python, Django, Database, ML, Sensors

with Diagram("AI Fire Monitoring System", show=False):

    sensors = Sensors("Sensors")
    ml = ML("ML Engine")
    django = Django("Django Backend")
    database = Database("Database")

    sensors >> ml >> django >> database
