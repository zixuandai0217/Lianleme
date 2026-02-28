"""
营养计算器
基于科学公式计算 BMR、TDEE 等
"""


def calculate_bmr(weight: float, height: float, age: int, gender: int) -> float:
    """
    计算基础代谢率 (BMR) - Mifflin-St Jeor 公式

    Args:
        weight: 体重 kg
        height: 身高 cm
        age: 年龄
        gender: 性别 (1=男，2=女)

    Returns:
        BMR 值 (kcal/天)
    """
    if gender == 1:  # 男性
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:  # 女性
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    return round(bmr, 1)


def calculate_tdee(bmr: float, activity_level: str) -> float:
    """
    计算每日总消耗 (TDEE)

    Args:
        bmr: 基础代谢率
        activity_level: 活动水平
            - sedentary: 久坐（几乎不运动）
            - light: 轻度活动（每周 1-3 次）
            - moderate: 中度活动（每周 3-5 次）
            - active: 活跃（每周 6-7 次）
            - very_active: 非常活跃（体力工作 + 运动）

    Returns:
        TDEE 值 (kcal/天)
    """
    multipliers = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9
    }

    multiplier = multipliers.get(activity_level, 1.55)
    return round(bmr * multiplier, 1)


def calculate_target_calories(
    tdee: float,
    goal_type: str,
    weekly_goal: float = 0.5
) -> float:
    """
    计算目标摄入热量

    Args:
        tdee: 每日总消耗
        goal_type: 目标类型 (lose_weight/gain_muscle/maintain)
        weekly_goal: 每周目标变化 kg

    Returns:
        目标摄入热量 (kcal/天)
    """
    # 1kg 脂肪约等于 7700 kcal
    daily_adjustment = weekly_goal * 7700 / 7

    if goal_type == "lose_weight":
        # 减重：热量缺口
        target = tdee - daily_adjustment
        # 确保不低于安全值
        target = max(target, 1200)  # 女性最低 1200
    elif goal_type == "gain_muscle":
        # 增肌：热量盈余
        target = tdee + min(daily_adjustment, 500)
    else:  # maintain
        target = tdee

    return round(target)


def calculate_macros(calories: int, goal_type: str, weight: float) -> dict:
    """
    计算三大营养素分配

    Args:
        calories: 目标热量
        goal_type: 目标类型
        weight: 体重 kg

    Returns:
        包含蛋白质、碳水、脂肪的字典 (单位：g)
    """
    if goal_type == "lose_weight":
        # 减重：高蛋白、中低碳水
        protein_ratio = 0.35
        fat_ratio = 0.30
        carbs_ratio = 0.35
    elif goal_type == "gain_muscle":
        # 增肌：高蛋白、高碳水
        protein_ratio = 0.30
        fat_ratio = 0.25
        carbs_ratio = 0.45
    else:  # maintain
        # 维持：均衡
        protein_ratio = 0.30
        fat_ratio = 0.30
        carbs_ratio = 0.40

    # 1g 蛋白质 = 4kcal, 1g 碳水 = 4kcal, 1g 脂肪 = 9kcal
    protein_g = round((calories * protein_ratio) / 4)
    fat_g = round((calories * fat_ratio) / 9)
    carbs_g = round((calories * carbs_ratio) / 4)

    return {
        "protein": protein_g,
        "carbohydrates": carbs_g,
        "fat": fat_g
    }


def calculate_bmi(weight: float, height: float) -> float:
    """
    计算 BMI 指数

    Args:
        weight: 体重 kg
        height: 身高 cm

    Returns:
        BMI 值
    """
    height_m = height / 100
    if height_m <= 0:
        return 0
    bmi = weight / (height_m ** 2)
    return round(bmi, 1)


def get_bmi_category(bmi: float) -> str:
    """
    获取 BMI 分类

    Returns:
        BMI 分类字符串
    """
    if bmi < 18.5:
        return "underweight"  # 偏瘦
    elif bmi < 24:
        return "normal"  # 正常
    elif bmi < 28:
        return "overweight"  # 偏胖
    else:
        return "obese"  # 肥胖


def calculate_age(birthday: str) -> int:
    """
    根据生日计算年龄

    Args:
        birthday: 生日字符串 (YYYY-MM-DD)

    Returns:
        年龄
    """
    from datetime import date

    if not birthday:
        return 30  # 默认值

    try:
        birth_date = date.fromisoformat(birthday)
        today = date.today()
        age = today.year - birth_date.year

        # 如果今年生日还没到，减 1 岁
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1

        return max(1, min(100, age))
    except (ValueError, TypeError):
        return 30  # 默认值


def calculate_all(
    weight: float,
    height: float,
    age: int,
    gender: int,
    activity_level: str,
    goal_type: str,
    weekly_goal: float = 0.5
) -> dict:
    """
    一次性计算所有营养数据

    Returns:
        包含所有计算结果的字典
    """
    bmr = calculate_bmr(weight, height, age, gender)
    tdee = calculate_tdee(bmr, activity_level)
    target_calories = calculate_target_calories(tdee, goal_type, weekly_goal)
    macros = calculate_macros(target_calories, goal_type, weight)
    bmi = calculate_bmi(weight, height)

    return {
        "bmr": bmr,
        "tdee": tdee,
        "target_calories": target_calories,
        "protein": macros["protein"],
        "carbohydrates": macros["carbohydrates"],
        "fat": macros["fat"],
        "bmi": bmi,
        "bmi_category": get_bmi_category(bmi)
    }
