from locust import HttpUser, between, task


class FireMonitoringUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def home(self):
        self.client.get("/")
