from locust import HttpUser, task, between


class SampleApiUser(HttpUser):
    wait_time = between(0.05, 0.3)

    @task(6)
    def root(self):
        self.client.get("/", name="GET /")

    @task(3)
    def page_a(self):
        self.client.get("/a", name="GET /a")

    @task(1)
    def page_b(self):
        self.client.get("/b", name="GET /b")
