import os

from fastapi import FastAPI

from app.routes.internal import router as internal_router

app = FastAPI(title='Lianleme AI Coach Service', version='1.0.0')


@app.get('/health')
async def health() -> dict:
    return {
        'status': 'ok',
        'service': 'ai-coach-service',
        'text_model': os.getenv('TEXT_MODEL', 'deepseek-v3.2'),
        'vision_model': os.getenv('VISION_MODEL', 'qwen3-vl-flash'),
    }


app.include_router(internal_router)


if __name__ == '__main__':
    import uvicorn

    # shift the standalone AI coach service default port away from common local collisions; local service startup only; verify with http://127.0.0.1:18020/health
    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '18020')))
