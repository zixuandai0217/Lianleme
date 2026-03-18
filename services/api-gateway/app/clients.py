import httpx


async def post_json(base_url: str, path: str, payload: dict) -> dict | None:
    # Why: explicit names reduce ambiguity between outgoing request data and response data.
    # Scope: all gateway outbound POST calls to internal services.
    # Verify: gateway integration tests still return expected JSON payloads.
    target_url = f"{base_url.rstrip('/')}" + path
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(target_url, json=payload)
            if response.is_success:
                return response.json()
    except Exception:
        return None
    return None


async def get_json(base_url: str, path: str) -> dict | None:
    target_url = f"{base_url.rstrip('/')}" + path
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(target_url)
            if response.is_success:
                return response.json()
    except Exception:
        return None
    return None
