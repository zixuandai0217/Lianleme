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

    uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8020')))
