from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_photo_task_lifecycle() -> None:
    resp = client.post('/internal/photo/analyze', json={'user_id': 'u1', 'image_url': 'http://x/y.jpg'})
    assert resp.status_code == 200
    task_id = resp.json()['task_id']

    detail = client.get(f'/internal/photo/tasks/{task_id}')
    assert detail.status_code == 200
    assert detail.json()['task_id'] == task_id


def test_weekly_report_endpoint() -> None:
    resp = client.get('/internal/report/weekly/u1')
    assert resp.status_code == 200
    assert 'ai_suggestion' in resp.json()
