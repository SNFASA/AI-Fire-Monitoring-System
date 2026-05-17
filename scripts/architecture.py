# scripts/architecture.py
from diagrams import Cluster, Diagram
from diagrams.generic.database import SQL
from diagrams.generic.device import Tablet
from diagrams.programming.framework import Django
from diagrams.programming.language import Python

with Diagram(
    "AI Fire Monitoring System Architecture",
    show=False,
    filename="architecture_diagram",
):
    with Cluster("Data Source"):
        sensors = Tablet("IOT Sensors")

    with Cluster("Processing"):
        ml_engine = Python("ML Engine")
        backend = Django("Django Backend")

    database = SQL("PostgreSQL")

    sensors >> ml_engine >> backend >> database
