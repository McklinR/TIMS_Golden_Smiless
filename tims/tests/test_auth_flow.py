import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TIMS_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TIMS_SECRET_KEY", "test-secret")

from backend.main import app


class AuthFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.get("/api/health")

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_login_returns_flat_payload(self):
        response = self.client.post(
            "/api/auth/login",
            data={"username": "director", "password": "director123"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["role"], "ADMIN")
        self.assertEqual(data["full_name"], "Company Director")
        self.assertNotIn("user", data)

    def test_director_can_create_other_users(self):
        director_login = self.client.post(
            "/api/auth/login",
            data={"username": "director", "password": "director123"},
        )
        director_token = director_login.json()["access_token"]

        response = self.client.post(
            "/users",
            headers={"Authorization": f"Bearer {director_token}"},
            json={
                "username": "musa",
                "full_name": "Musa Ndlovu",
                "password": "musa123",
                "role": "TRACKING",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "musa")
        self.assertEqual(data["role"], "TRACKING")
        self.assertEqual(data["full_name"], "Musa Ndlovu")


if __name__ == "__main__":
    unittest.main()
