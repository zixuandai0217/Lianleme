from fastapi import FastAPI
from pydantic import BaseModel


class ProfilePayload(BaseModel):
    nickname: str
    height_cm: float
    weight_kg: float
    target_weight_kg: float


store: dict[str, dict] = {}


app = FastAPI(title="Lianleme Profile Service", version="1.0.0")


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok', 'service': 'profile-service'}


@app.get('/internal/users/{user_id}/profile')
async def get_profile(user_id: str) -> dict:
    return store.get(
        user_id,
        {
            'user_id': user_id,
            'nickname': '练了么用户',
            'height_cm': 170,
            'weight_kg': 70,
            'target_weight_kg': 65,
        },
    )


@app.post('/internal/users/{user_id}/profile')
async def set_profile(user_id: str, payload: ProfilePayload) -> dict:
    # Why: profile-service is the source of truth for profile snapshots.
    # Scope: all profile read/write requests from gateway aggregate APIs.
    # Verify: call GET after POST and ensure fields persist.
    profile = {'user_id': user_id, **payload.model_dump()}
    store[user_id] = profile
    return profile


if __name__ == '__main__':
    import os
    import uvicorn

    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8010')))
