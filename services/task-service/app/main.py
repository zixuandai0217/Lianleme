import os

from fastapi import FastAPI

from app.routes import router as internal_router

app = FastAPI(title='Lianleme Task Service', version='1.0.0')


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok', 'service': 'task-service'}


app.include_router(internal_router)


if __name__ == '__main__':
    import uvicorn

    # shift the standalone task-service default port away from common local collisions; local service startup only; verify with http://127.0.0.1:18030/health
    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '18030')))
