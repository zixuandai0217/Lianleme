"""
AI 服务封装 - 通义千问
"""
import httpx
import json
import logging
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """通义千问 AI 服务"""

    def __init__(self):
        self.api_key = settings.ALIYUN_API_KEY
        self.base_url = settings.ALIYUN_API_BASE_URL
        self.model = settings.AI_MODEL
        self.max_tokens = settings.AI_MAX_TOKENS
        self.temperature = settings.AI_TEMPERATURE

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        调用通义千问聊天 API

        Args:
            messages: 消息历史 [{"role": "user", "content": "你好"}]
            model: 模型名称（可选）
            temperature: 温度（可选）
            max_tokens: 最大 token 数（可选）

        Returns:
            AI 回复的文本
        """
        if not self.api_key:
            logger.warning("AI API Key 未配置")
            return "AI 服务暂未配置，请联系管理员。"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/services/aigc/text-generation/generation",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model or self.model,
                        "input": {"messages": messages},
                        "parameters": {
                            "temperature": temperature or self.temperature,
                            "max_tokens": max_tokens or self.max_tokens
                        }
                    }
                )

                if response.status_code != 200:
                    logger.error(f"AI API 请求失败：{response.status_code} - {response.text}")
                    return f"AI 服务响应失败（状态码：{response.status_code}）"

                result = response.json()

                # 解析响应
                if "output" in result and "text" in result["output"]:
                    return result["output"]["text"]
                else:
                    logger.error(f"AI API 响应格式异常：{result}")
                    return "AI 服务响应格式异常"

        except httpx.TimeoutException:
            logger.error("AI API 请求超时")
            return "AI 服务响应超时，请稍后再试。"
        except Exception as e:
            logger.error(f"AI API 调用失败：{str(e)}")
            return f"AI 服务调用失败：{str(e)}"

    async def generate_diet_plan(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成饮食计划

        Args:
            user_data: 用户数据字典

        Returns:
            饮食计划（JSON 格式）
        """
        prompt = self._build_diet_prompt(user_data)

        messages = [
            {
                "role": "system",
                "content": """你是一位专业的营养师，擅长制定个性化的科学饮食计划。
请根据用户信息生成详细的饮食方案。

要求：
1. 必须返回纯 JSON 格式，不要包含任何解释文字
2. JSON 格式参考：{
  "dailyCalories": 数字，
  "protein": 数字（克），
  "carbohydrates": 数字（克），
  "fat": 数字（克），
  "water": 数字（毫升），
  "meals": {
    "breakfast": {"calories": 数字，"foods": [{"name": "食物名", "grams": 数字，"calories": 数字}]},
    "lunch": {...},
    "dinner": {...},
    "snacks": {...}
  }
}
3. 食物选择要符合中国饮食习惯
4. 考虑用户的过敏食物和饮食偏好"""
            },
            {"role": "user", "content": prompt}
        ]

        response = await self.chat(messages)

        # 尝试解析 JSON
        try:
            # 清理响应，移除可能的 markdown 标记
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            return json.loads(clean_response)
        except json.JSONDecodeError as e:
            logger.error(f"饮食计划 JSON 解析失败：{str(e)}, 响应内容：{response}")
            # 返回默认计划
            return self._get_default_diet_plan(user_data)

    async def generate_workout_plan(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成运动计划

        Args:
            user_data: 用户数据字典

        Returns:
            运动计划（JSON 格式）
        """
        prompt = self._build_workout_prompt(user_data)

        messages = [
            {
                "role": "system",
                "content": """你是一位专业的健身教练，擅长制定个性化的科学训练计划。
请根据用户信息生成详细的运动方案。

要求：
1. 必须返回纯 JSON 格式，不要包含任何解释文字
2. JSON 格式参考：{
  "weeklyWorkoutDays": 数字，
  "estimatedCaloriesBurn": 数字，
  "weekPlan": [
    {"day": 数字，"type": "类型", "name": "名称", "duration": 数字，"difficulty": "难度",
     "exercises": [{"name": "动作名", "sets": 数字，"reps": 数字，"restSeconds": 数字}]}
  ]
}
3. 训练类型包括：cardio（有氧）、strength（力量）、flexibility（柔韧）、rest（休息）
4. 难度级别：beginner（初级）、intermediate（中级）、advanced（高级）
5. 动作要适合居家训练，不需要专业器械"""
            },
            {"role": "user", "content": prompt}
        ]

        response = await self.chat(messages)

        try:
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            return json.loads(clean_response)
        except json.JSONDecodeError:
            logger.error(f"运动计划 JSON 解析失败，响应内容：{response}")
            return self._get_default_workout_plan(user_data)

    async def chat_consultant(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        AI 健康顾问对话

        Args:
            message: 用户消息
            history: 历史对话
            context: 上下文数据（今日摄入、运动等）

        Returns:
            AI 回复
        """
        context_str = self._format_context(context) if context else ""

        system_prompt = f"""你是一位专业的 AI 健康顾问，专注于科学减肥和健身指导。
你的职责：
1. 解答用户关于减肥、健身、营养的问题
2. 提供科学、实用的建议
3. 鼓励用户，保持积极正面的态度
4. 避免提供医疗建议，如有健康问题建议咨询医生
{context_str}

请用中文回复，语气亲切、专业、鼓励性。"""

        messages = [{"role": "system", "content": system_prompt}]

        # 添加历史对话（最多 10 轮）
        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": message})

        return await self.chat(messages)

    def _build_diet_prompt(self, data: Dict[str, Any]) -> str:
        """构建饮食计划提示词"""
        gender_str = "男" if data.get("gender") == 1 else "女"
        goal_map = {
            "lose_weight": "减重",
            "gain_muscle": "增肌",
            "maintain": "维持"
        }

        return f"""请为用户生成个性化饮食计划：

【用户信息】
- 性别：{gender_str}
- 身高：{data.get("height", 0)}cm
- 体重：{data.get("weight", 0)}kg
- 年龄：{data.get("age", 30)}岁
- 目标：{goal_map.get(data.get("goal_type"), "减重")}
- 每周目标：{data.get("weekly_goal", 0.5)}kg
- 活动水平：{data.get("activity_level", "moderate")}

【营养计算】
- BMR: {data.get("bmr", 0)} kcal
- TDEE: {data.get("tdee", 0)} kcal
- 目标摄入：{data.get("target_calories", 1800)} kcal

【特殊要求】
- 过敏食物：{", ".join(data.get("allergies", [])) or "无"}
- 饮食偏好：{", ".join(data.get("preferences", [])) or "无"}
- 避免食物：{", ".join(data.get("avoid_foods", [])) or "无"}

请生成详细的饮食计划（JSON 格式）。"""

    def _build_workout_prompt(self, data: Dict[str, Any]) -> str:
        """构建运动计划提示词"""
        gender_str = "男" if data.get("gender") == 1 else "女"
        goal_map = {
            "lose_weight": "减重",
            "gain_muscle": "增肌",
            "maintain": "维持"
        }

        return f"""请为用户生成个性化运动计划：

【用户信息】
- 性别：{gender_str}
- 身高：{data.get("height", 0)}cm
- 体重：{data.get("weight", 0)}kg
- 年龄：{data.get("age", 30)}岁
- 目标：{goal_map.get(data.get("goal_type"), "减重")}
- 活动水平：{data.get("activity_level", "moderate")}
- 每周可运动：{data.get("exercise_days", 5)}天

请生成详细的运动计划（JSON 格式）。"""

    def _format_context(self, context: Dict[str, Any]) -> str:
        """格式化上下文"""
        lines = ["【今日数据】"]

        if "calories_in" in context:
            lines.append(f"- 已摄入：{context['calories_in']} kcal")
        if "calories_out" in context:
            lines.append(f"- 已消耗：{context['calories_out']} kcal")
        if "workout_status" in context:
            lines.append(f"- 今日运动：{context['workout_status']}")
        if "diet_status" in context:
            lines.append(f"- 饮食计划：{context['diet_status']}")

        return "\n".join(lines)

    def _get_default_diet_plan(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """返回默认饮食计划"""
        target_calories = user_data.get("target_calories", 1800)
        return {
            "dailyCalories": target_calories,
            "protein": 120,
            "carbohydrates": 200,
            "fat": 60,
            "water": 2000,
            "meals": {
                "breakfast": {
                    "calories": int(target_calories * 0.25),
                    "foods": [
                        {"name": "燕麦片", "grams": 50, "calories": 180},
                        {"name": "鸡蛋", "grams": 50, "calories": 80},
                        {"name": "牛奶", "ml": 250, "calories": 135}
                    ]
                },
                "lunch": {
                    "calories": int(target_calories * 0.35),
                    "foods": [
                        {"name": "糙米饭", "grams": 150, "calories": 175},
                        {"name": "鸡胸肉", "grams": 150, "calories": 165},
                        {"name": "西兰花", "grams": 200, "calories": 70}
                    ]
                },
                "dinner": {
                    "calories": int(target_calories * 0.30),
                    "foods": [
                        {"name": "鱼肉", "grams": 150, "calories": 180},
                        {"name": "蔬菜沙拉", "grams": 200, "calories": 80},
                        {"name": "红薯", "grams": 100, "calories": 86}
                    ]
                },
                "snacks": {
                    "calories": int(target_calories * 0.10),
                    "foods": [
                        {"name": "坚果", "grams": 20, "calories": 120},
                        {"name": "苹果", "grams": 100, "calories": 52}
                    ]
                }
            }
        }

    def _get_default_workout_plan(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """返回默认运动计划"""
        return {
            "weeklyWorkoutDays": 5,
            "estimatedCaloriesBurn": 300,
            "weekPlan": [
                {"day": 1, "type": "cardio", "name": "HIIT 燃脂训练", "duration": 30, "difficulty": "intermediate",
                 "exercises": [
                     {"name": "开合跳", "sets": 4, "reps": 30, "restSeconds": 30},
                     {"name": "深蹲", "sets": 4, "reps": 20, "restSeconds": 45},
                     {"name": "俯卧撑", "sets": 4, "reps": 15, "restSeconds": 45},
                     {"name": "登山跑", "sets": 4, "reps": 30, "restSeconds": 30}
                 ]},
                {"day": 2, "type": "strength", "name": "上肢力量训练", "duration": 40, "difficulty": "intermediate",
                 "exercises": [
                     {"name": "俯卧撑", "sets": 4, "reps": 15, "restSeconds": 60},
                     {"name": "椅子臂屈伸", "sets": 3, "reps": 12, "restSeconds": 45},
                     {"name": "平板支撑", "sets": 3, "reps": 45, "restSeconds": 45}
                 ]},
                {"day": 3, "type": "rest", "name": "休息日", "duration": 0, "difficulty": "beginner", "exercises": []},
                {"day": 4, "type": "cardio", "name": "有氧训练", "duration": 35, "difficulty": "intermediate",
                 "exercises": [
                     {"name": "原地慢跑", "sets": 1, "reps": 300, "restSeconds": 0},
                     {"name": "高抬腿", "sets": 4, "reps": 30, "restSeconds": 30},
                     {"name": "波比跳", "sets": 4, "reps": 10, "restSeconds": 60}
                 ]},
                {"day": 5, "type": "strength", "name": "下肢力量训练", "duration": 40, "difficulty": "intermediate",
                 "exercises": [
                     {"name": "深蹲", "sets": 4, "reps": 20, "restSeconds": 60},
                     {"name": "弓步蹲", "sets": 3, "reps": 15, "restSeconds": 45},
                     {"name": "臀桥", "sets": 3, "reps": 20, "restSeconds": 45}
                 ]},
                {"day": 6, "type": "flexibility", "name": "瑜伽拉伸", "duration": 30, "difficulty": "beginner",
                 "exercises": [
                     {"name": "猫牛式", "sets": 1, "reps": 60, "restSeconds": 0},
                     {"name": "下犬式", "sets": 3, "reps": 30, "restSeconds": 15},
                     {"name": "鸽子式", "sets": 2, "reps": 60, "restSeconds": 15}
                 ]},
                {"day": 7, "type": "rest", "name": "休息日", "duration": 0, "difficulty": "beginner", "exercises": []}
            ]
        }


# 单例
ai_service = AIService()
