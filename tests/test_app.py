import os, tempfile
from fastapi.testclient import TestClient

def test_task_router_core_flow():
    import app
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_path = app.DB_PATH
    app.DB_PATH = path
    app.init_db()
    # Use lifespan so the app is initialized; async routing is not awaited in these API checks.
    with TestClient(app.app) as client:
        assert client.get("/api/health").json()["ok"] is True
        contributors = client.get("/api/contributors").json()
        assert len(contributors) >= 1
        created = client.post("/api/tasks", json={
            "title": "Test data review", "description": "test", "expertise": "data analysis", "priority": "normal"
        })
        assert created.status_code == 200
        task_id = created.json()["id"]
        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["task"]["title"] == "Test data review"
        assert len(detail.json()["events"]) >= 1
    app.DB_PATH = old_path
    os.remove(path)
