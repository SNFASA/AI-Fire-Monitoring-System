# scripts/architecture.py
from diagrams import Diagram, Cluster
from diagrams.programming.framework import Django
from diagrams.programming.language import Python
from diagrams.generic.database import SQL
from diagrams.generic.device import Tablet

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
