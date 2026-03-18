from langchain.tools import tool


@tool
def nutrition_hint_tool(goal: str) -> str:
    """Return a short nutrition hint by goal."""
    if "减脂" in goal or "lose" in goal:
        return "优先高蛋白和高纤维，晚餐控制精制碳水。"
    if "增肌" in goal:
        return "确保每日蛋白摄入稳定，并在训练后补充碳水。"
    return "保持均衡饮食并记录每日总热量。"


@tool
def workout_template_tool(level: str) -> str:
    """Return a quick workout template by user level."""
    if level == "beginner":
        return "每周4次：2次力量+2次快走/慢跑，每次30-45分钟。"
    if level == "advanced":
        return "每周5-6次：力量分化训练+2次有氧，含1次恢复日。"
    return "每周5次：3次力量+2次有氧，配合拉伸和核心训练。"
