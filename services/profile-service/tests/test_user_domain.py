from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_profile_round_trip() -> None:
    payload = {'nickname': '测试用户', 'height_cm': 175, 'weight_kg': 68, 'target_weight_kg': 64}
    set_resp = client.post('/internal/users/u_1/profile', json=payload)
    assert set_resp.status_code == 200

    get_resp = client.get('/internal/users/u_1/profile')
    assert get_resp.status_code == 200
    assert get_resp.json()['nickname'] == '测试用户'
