from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_three_tab_home_endpoints() -> None:
    assert client.get('/v1/home/workout').status_code == 200
    assert client.get('/v1/home/diet').status_code == 200
    assert client.get('/v1/home/progress').status_code == 200


def test_plan_generate_contract() -> None:
    response = client.post(
        '/v1/plan/generate',
        json={'user_id': 'u_demo', 'plan_type': 'workout', 'objective': 'lose fat'},
    )
    assert response.status_code == 200
    body = response.json()
    assert 'plan_id' in body
    assert body['plan_type'] == 'workout'


def test_admin_endpoints() -> None:
    assert client.get('/v1/admin/dashboard').status_code == 200
    assert client.get('/v1/admin/users').status_code == 200
    assert client.get('/v1/admin/recipes').status_code == 200
    assert client.get('/v1/admin/workout-templates').status_code == 200
    assert client.get('/v1/admin/ai-config').status_code == 200
