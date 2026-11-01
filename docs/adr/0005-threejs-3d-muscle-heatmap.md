# ADR-0005: 采用 Three.js 实现 3D 肌肉热力图

## 状态

已接受 (2026-10-27)

## 背景

当前体型分析（VisionGraph）输出 `muscle_scores`：
```json
{
  "胸部": 7,
  "背部": 6,
  "核心": 4,
  "腿部": 5,
  "手臂": 8,
  "肩部": 7
}
```

但前端只有**文字展示**：
```
胸部：7/10 ⭐⭐⭐⭐⭐⭐⭐
背部：6/10 ⭐⭐⭐⭐⭐⭐
...
```

这种展示方式：
1. **不够直观**：用户需要逐条阅读，无法快速理解整体体型
2. **缺少视觉冲击**：作为简历项目，缺少"wow"效果
3. **无法对比**：历史记录之间的对比只能看数字

为了提升项目的视觉亮点和用户体验，需要引入 **3D 可视化**。

## 决策

使用 **Three.js** 实现 **3D 肌肉热力图**，展示用户的体型分析结果。

### 核心特性

1. **3D 人体模型**
   - 从开源库（Sketchfab/Mixamo）获取人体模型（GLB/GLTF 格式）
   - 分为 12 个肌肉区域（胸部、上背、下背、腹肌、斜方肌、肩、手臂、前臂、臀、大腿前、大腿后、小腿）
   - 用户可旋转、缩放模型查看细节

2. **材质发光**
   - 分数 0-10 映射到**材质发光强度**：低分暗淡，高分发光明亮
   - 使用 Three.js MeshStandardMaterial 的 emissive 属性

3. **对比功能**
   - **初始态 → 最终态**：显示两个 3D 模型并排，箭头标注变化
   - **AI 预测**：根据当前状态 + 训练计划，预测 8 周后的样子（LLM + 规则混合）
   - **手动对比**：用户选择任意两次体型分析记录对比

### 技术架构

#### 前端（React + Three.js）

```tsx
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useGLTF } from '@react-three/drei'

function MuscleHeatmap({ muscleScores }: { muscleScores: Record<string, number> }) {
  const { scene } = useGLTF('/models/human-body.glb')
  
  // 根据分数设置每个肌肉区域的发光强度
  useEffect(() => {
    Object.entries(muscleScores).forEach(([muscle, score]) => {
      const mesh = scene.getObjectByName(muscle) as THREE.Mesh
      if (mesh && mesh.material instanceof THREE.MeshStandardMaterial) {
        // 分数越高，发光越亮
        const emissiveIntensity = score / 10
        mesh.material.emissive.set(scoreToEmissiveColor(score))
        mesh.material.emissiveIntensity = emissiveIntensity
      }
    })
  }, [muscleScores, scene])
  
  return (
    <Canvas camera={{ position: [0, 1, 3], fov: 50 }}>
      <ambientLight intensity={0.3} />
      <directionalLight position={[5, 5, 5]} intensity={0.5} />
      <primitive object={scene} />
      <OrbitControls />
    </Canvas>
  )
}

function scoreToEmissiveColor(score: number): THREE.Color {
  // 低分暗红，高分亮黄
  const hue = score / 10 * 60 // 0=红, 60=黄
  return new THREE.Color().setHSL(hue / 360, 1, 0.5)
}
```

#### 模型获取与精简

1. **开源模型库**：Sketchfab 搜索 "human anatomy muscle"（选择 CC-BY 许可证）
2. **Three.js 代码精简**：
   - 加载模型后，遍历场景树删除不需要的 Mesh（如面部细节、手指）
   - 只保留 12 个肌肉区域对应的 Mesh，按约定命名（chest, upper_back, lower_back, ...）
   - 压缩纹理，目标体积 1-2MB
3. **导出格式**：GLB（二进制 GLTF，体积最小）

**备选方案**：如果找不到合适的开源模型，用 Three.js 代码生成简化的 3D 人体（基础几何体拼装）。

#### AI 预测实现

```python
# 后端 API: POST /api/vision/predict
async def predict_future_body(
    current_analysis: BodyAnalysis,
    training_plan: TrainingPlan,
    user_goal: str  # "增肌" | "减脂" | "维持"
) -> BodyAnalysis:
    # LLM 直接预测
    prompt = f"""
    用户当前肌肉评分：{current_analysis.muscle_scores}
    训练计划：{training_plan.summary}
    目标：{user_goal}
    
    预测 8 周后的肌肉评分（0-10），输出 JSON 格式：
    {{
      "胸部": <预测分数>,
      "背部": <预测分数>,
      ...
    }}
    
    注意：预测要合理，8 周内单个肌群最多提升 2 分。
    """
    
    llm_prediction = await llm.ainvoke(prompt)
    
    return BodyAnalysis(muscle_scores=llm_prediction)
```

### MVP 实现范围

为了在 2 周内完成，MVP 包含：
1. ✅ **3D 模型加载**（开源模型 + Three.js 渲染）
2. ✅ **颜色映射**（分数 → 颜色渐变）
3. ✅ **旋转控制**（OrbitControls）
4. ✅ **初始态 → 最终态对比**（并排显示两个模型）
5. ⏸️ **AI 预测**（后续迭代，MVP 阶段只做手动选择历史记录对比）

## 后果

### 优势

1. **视觉冲击力强**
   - 3D 模型比文字列表更直观
   - 作为简历项目，面试时打开网页展示，效果远超纯文字项目

2. **技术栈多样化**
   - 展示前端 3D 渲染能力（Three.js / WebGL）
   - 展示 3D 资源处理能力（Blender / 模型优化）

3. **用户体验提升**
   - 用户可以旋转模型，从不同角度查看
   - 对比功能让进步可视化（如"胸部从 5 分提升到 7 分"）

4. **可扩展性**
   - 后续可以加入动画（如肌肉收缩）
   - 可以加入姿态检测数据（如标注错误动作的部位）

### 权衡

1. **模型资源依赖**
   - 需要找到合适的开源人体模型（或自己建模）
   - 模型体积需要控制在 1-2MB（首次加载时间 < 3 秒）
   - **缓解方案**：使用 CDN 加速，或延迟加载（用户切换到"体型分析"页面时再加载）

2. **浏览器兼容性**
   - Three.js 需要 WebGL 支持（现代浏览器均支持）
   - 移动端性能可能较差（复杂模型渲染卡顿）
   - **缓解方案**：本地运行为主，移动端暂不支持

3. **开发学习曲线**
   - 需要学习 Three.js / React Three Fiber
   - 需要学习模型加载、材质操作、场景管理
   - **缓解方案**：MVP 阶段使用最简单的模型和代码，后续迭代再优化

4. **肌肉分区对齐问题**
   - 开源模型可能没有按 12 个区域命名（如"胸部"可能叫 "pectoralis"）
   - **缓解方案**：代码中维护映射表，或用 Three.js 重命名 Mesh

5. **AI 预测准确性**
   - LLM 预测可能过于乐观或悲观
   - **缓解方案**：Prompt 中明确约束（8 周最多提升 2 分）+ 标注"预测值，仅供参考"

## 备选方案

### 方案 A：2D SVG 人体轮廓 + 颜色填充

```tsx
<svg viewBox="0 0 200 400">
  <path d="M100,50 L120,100..." fill={scoreToColor(muscleScores['胸部'])} />
  <path d="M80,100 L100,150..." fill={scoreToColor(muscleScores['背部'])} />
</svg>
```

**优势**：
- 实现简单（1-2 天完成）
- 体积小（几 KB）
- 兼容性好

**未采用原因**：
- 视觉效果不如 3D
- 技术含量不足，简历亮点不够
- 无法展示 Three.js 技术栈

### 方案 B：基于真实照片的热力图

在用户上传的照片上叠加半透明色块（类似医学影像的热力图）。

**未采用原因**：
- 照片姿态不同，色块位置难以对齐
- 隐私问题：用户可能不愿意照片上有标注
- 对比功能难实现（不同照片的背景、光线不一致）

### 方案 C：购买商业 3D 模型

从 TurboSquid / CGTrader 购买高质量人体肌肉模型（$50-$200）。

**未采用原因**：
- 成本高（个人项目预算有限）
- 许可证可能不允许开源
- 开源模型已经足够满足需求

### 方案 D：不做 3D，只做雷达图

```tsx
<ResponsiveRadar
  data={[{ muscle: '胸部', score: 7 }, ...]}
  keys={['score']}
  indexBy="muscle"
/>
```

**未采用原因**：
- 雷达图是常见方案，无亮点
- 作为简历项目，需要展示技术广度
- 3D 可视化更有视觉冲击力

## 相关决策

- [ADR-0002](0002-mediapipe-pose-detection.md) - 姿态检测数据后续可叠加到 3D 模型上
