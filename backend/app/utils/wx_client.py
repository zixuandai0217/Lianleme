"""微信 API 封装：登录、订阅消息推送"""
import httpx

from app.core.config import settings


class WxClient:
    """微信 API 客户端封装"""

    _access_token: str = ""
    _token_expires_at: float = 0.0

    async def get_access_token(self) -> str:
        """获取微信 access_token（带缓存，过期自动刷新）"""
        import time
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": settings.WECHAT_APP_ID,
            "secret": settings.WECHAT_APP_SECRET,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败：{data}")
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)
        return self._access_token

    async def send_subscribe_message(
        self, openid: str, template_id: str, data: dict, page: str = "pages/index/index"
    ) -> dict:
        """发送微信订阅消息"""
        token = await self.get_access_token()
        url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"
        payload = {
            "touser": openid,
            "template_id": template_id,
            "page": page,
            "data": data,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
        if result.get("errcode", 0) != 0:
            raise RuntimeError(f"订阅消息发送失败：{result}")
        return result

    async def code2session(self, code: str) -> dict:
        """微信登录：code 换取 openid + session_key"""
        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": settings.WECHAT_APP_ID,
            "secret": settings.WECHAT_APP_SECRET,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            return resp.json()
