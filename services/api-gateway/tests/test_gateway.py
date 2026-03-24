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


def test_auth_login_accepts_email_and_password() -> None:
    # simplify the mock auth contract to email/password so the mobile client can use one minimal login form; gateway auth endpoints only; verify with `uv run pytest services/api-gateway/tests/test_gateway.py -k auth`.
    response = client.post(
        '/v1/auth/login',
        json={'email': 'demo@example.com', 'password': 'secret123'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['email'] == 'demo@example.com'
    assert body['user_id'].startswith('u_')


def test_auth_register_auto_logs_in_with_email_and_password() -> None:
    # keep registration as the same minimal email/password demo flow so the client can enter the app without a second auth step; gateway auth endpoints only; verify with `uv run pytest services/api-gateway/tests/test_gateway.py -k auth`.
    response = client.post(
        '/v1/auth/register',
        json={'email': 'fresh@example.com', 'password': 'secret123'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['token_type'] == 'bearer'
    assert body['email'] == 'fresh@example.com'
    assert body['user_id'].startswith('u_')
