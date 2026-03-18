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

    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8030')))
