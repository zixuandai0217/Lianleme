/* Three.js runtime for the 3D muscle heatmap — lazy by construction.
 *
 * Nothing in this module imports three at module scope: the two dynamic imports
 * inside `createMuscleHeatmapRuntime` are the only way the 3D runtime can enter
 * a page. The analysis page therefore stays usable without WebGL, and three is
 * emitted as a separate chunk by Vite.
 *
 * The pure helpers (orbit clamps, HSL → RGB, layout, fallback probing, model
 * cache) are exported so they can be asserted without a browser or a GPU.
 */
import {
  MUSCLE_REGIONS,
  NEUTRAL_INTENSITY,
  buildHeatmapScene,
  type HeatmapCapability,
  type HeatmapDiff,
  type HeatmapScene,
  type MuscleLevel,
  type MuscleRegion,
  type MuscleVisual,
} from "@/muscle-heatmap"

export const MODEL_URL = "/models/muscle-body.glb"
export const MODEL_LOAD_TIMEOUT_MS = 8_000
export const MAX_MODEL_INSTANCES = 2

export const MIN_DISTANCE = 2.6
export const MAX_DISTANCE = 6
export const MIN_POLAR_ANGLE = 0.45
export const MAX_POLAR_ANGLE = 1.48
export const DEFAULT_DISTANCE = 4.4
export const DEFAULT_POLAR_ANGLE = 1.22
export const CAMERA_TARGET_Y = 1.05
export const STACK_BREAKPOINT = 720

export type HeatmapLayout = "split" | "stacked"

export interface OrbitState {
  distance: number
  polar: number
}

export interface Rgb {
  r: number
  g: number
  b: number
}

export interface EmissiveVisual extends Rgb {
  intensity: number
}

export interface RegionDescription {
  region: MuscleRegion
  label: string
  scoreText: string
  level: MuscleLevel
  evaluated: boolean
  isWeak: boolean
  weakLabel: "弱势肌群" | null
  advice: string
  ariaLabel: string
}

const REGION_SET: ReadonlySet<string> = new Set(MUSCLE_REGIONS)

const LEVEL_ADVICE: Readonly<Record<MuscleLevel, string>> = {
  偏弱: "优先补基础力量，从轻重量、多次数开始。",
  待加强: "每周安排两次针对性训练，先保证动作质量。",
  中等: "维持当前训练量，可逐步增加负重。",
  良好: "保持训练频率，注意与弱势部位平衡。",
  优秀: "状态很好，保持当前节奏并注意恢复。",
  未评估: "这次分析没有评估该部位，请参考其他部位。",
}

/** Narrow screens stack the comparison instead of squeezing two bodies. */
export function layoutForWidth(width: number): HeatmapLayout {
  if (!Number.isFinite(width)) return "stacked"
  return width < STACK_BREAKPOINT ? "stacked" : "split"
}

/** Clamp the orbit so the camera can never enter the body or go under ground. */
export function clampOrbit(state: OrbitState): OrbitState {
  const distance = Number.isFinite(state.distance) ? state.distance : DEFAULT_DISTANCE
  const polar = Number.isFinite(state.polar) ? state.polar : DEFAULT_POLAR_ANGLE
  return {
    distance: Math.min(MAX_DISTANCE, Math.max(MIN_DISTANCE, distance)),
    polar: Math.min(MAX_POLAR_ANGLE, Math.max(MIN_POLAR_ANGLE, polar)),
  }
}

/** ADR-0005 hue ramp is HSL(hue, 1, 0.5); map it to linear emissive RGB. */
export function hueToRgb(hueDegrees: number): Rgb {
  const normalized = Number.isFinite(hueDegrees) ? ((hueDegrees % 360) + 360) % 360 : 0
  const sector = normalized / 60
  const x = 1 - Math.abs((sector % 2) - 1)

  if (sector < 1) return { r: 1, g: x, b: 0 }
  if (sector < 2) return { r: x, g: 1, b: 0 }
  if (sector < 3) return { r: 0, g: 1, b: x }
  if (sector < 4) return { r: 0, g: x, b: 1 }
  if (sector < 5) return { r: x, g: 0, b: 1 }
  return { r: 1, g: 0, b: x }
}

/** Unevaluated regions stay neutral grey: never the red of a zero score. */
export function emissiveForVisual(
  visual: Pick<MuscleVisual, "evaluated" | "hue" | "intensity">,
): EmissiveVisual {
  if (!visual.evaluated) {
    return { r: 0.55, g: 0.55, b: 0.55, intensity: NEUTRAL_INTENSITY }
  }
  const rgb = hueToRgb(visual.hue)
  return { ...rgb, intensity: Math.min(1, Math.max(0, visual.intensity)) }
}

export interface EmissiveMaterialLike {
  emissive: { setRGB(red: number, green: number, blue: number): unknown }
  emissiveIntensity: number
}

/**
 * Apply one region's visual to an existing material. Updating the same material
 * object is what lets a new score set reuse the WebGL context instead of
 * remounting the canvas.
 */
export function applyVisualToMaterial(
  material: EmissiveMaterialLike,
  visual: Pick<MuscleVisual, "evaluated" | "hue" | "intensity">,
): void {
  const emissive = emissiveForVisual(visual)
  material.emissive.setRGB(emissive.r, emissive.g, emissive.b)
  material.emissiveIntensity = emissive.intensity
}

/** Normalise analysis weak-muscle labels (e.g. "背") onto the 12 mesh regions. */
export function weakRegionsFromAnalysis(
  weakMuscles: readonly string[] | null | undefined,
): Set<MuscleRegion> {
  const regions = new Set<MuscleRegion>()
  if (!weakMuscles || weakMuscles.length === 0) return regions

  const scores: Record<string, number> = {}
  for (const muscle of weakMuscles) scores[muscle] = 0

  const scene = buildHeatmapScene(scores)
  for (const visual of scene.visuals) {
    if (visual.sourceKeys.length > 0) regions.add(visual.region)
  }
  return regions
}

export function describeRegion(visual: MuscleVisual, isWeak: boolean): RegionDescription {
  const scoreText = visual.evaluated ? `${visual.score}/10 · ${visual.level}` : "未评估"
  const weakLabel = isWeak ? "弱势肌群" : null
  return {
    region: visual.region,
    label: visual.label,
    scoreText,
    level: visual.level,
    evaluated: visual.evaluated,
    isWeak,
    weakLabel,
    advice: LEVEL_ADVICE[visual.level],
    ariaLabel: `${visual.label} ${scoreText}${weakLabel ? `，${weakLabel}` : ""}`,
  }
}

/** Screen-reader equivalent of the visible heatmap. */
export function buildAriaSummary(scene: HeatmapScene): string {
  const regions = scene.visuals
    .map((visual) =>
      visual.evaluated ? `${visual.label} ${visual.score} 分` : `${visual.label} 未评估`,
    )
    .join("，")
  const unmapped =
    scene.unmapped.length > 0 ? `；另有 ${scene.unmapped.length} 个部位未纳入 3D` : ""
  return `肌肉热力图：${regions}${unmapped}。`
}

/** Badge text for the region that changed the most between two analyses. */
export function annotationForDiff(diff: HeatmapDiff | null): string | null {
  const top = diff?.topChanges[0]
  if (!top) return null
  const delta = top.delta > 0 ? `+${top.delta}` : `${top.delta}`
  return `变化最大：${top.label} ${delta}`
}

/** One body for a single analysis, two for a comparison — never more. */
export function modelInstanceCount(compare: boolean): number {
  return compare ? MAX_MODEL_INSTANCES : 1
}

/** Probe WebGL before importing three or touching the model. */
export function probeHeatmapCapability(): HeatmapCapability {
  if (typeof document === "undefined" || typeof document.createElement !== "function") {
    return "probe-failed"
  }
  try {
    const canvas = document.createElement("canvas")
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl")
    return context ? "supported" : "unsupported"
  } catch {
    return "probe-failed"
  }
}

let modelBinaryPromise: Promise<ArrayBuffer> | null = null

/** Fetch the GLB once per session; a failure clears the cache so retry works. */
export function loadMuscleBodyBinary(fetchImpl: typeof fetch = fetch): Promise<ArrayBuffer> {
  if (!modelBinaryPromise) {
    modelBinaryPromise = (async () => {
      const response = await fetchImpl(MODEL_URL)
      if (!response.ok) throw new Error(`模型加载失败（HTTP ${response.status}）`)
      const buffer = await response.arrayBuffer()
      if (buffer.byteLength === 0) throw new Error("模型文件为空")
      return buffer
    })().catch((error: unknown) => {
      modelBinaryPromise = null
      throw error
    })
  }
  return modelBinaryPromise
}

/** Test-only hook: resets the per-session model cache. */
export function resetMuscleBodyCache(): void {
  modelBinaryPromise = null
}

export function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  message = "加载超时",
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeoutMs)
    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error: unknown) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

type ThreeModule = typeof import("three")

interface InstanceRuntime {
  scene: import("three").Scene
  camera: import("three").PerspectiveCamera
  meshes: Map<MuscleRegion, import("three").Mesh>
  materials: Map<MuscleRegion, import("three").MeshStandardMaterial>
  regionsByObjectId: Map<string, MuscleRegion>
}

export interface HeatmapRuntimeInput {
  scene: HeatmapScene
  compareScene: HeatmapScene | null
  highlightRegion: MuscleRegion | null
}

export interface HeatmapRuntimeOptions {
  onSelect?: (region: MuscleRegion | null) => void
}

export interface HeatmapRuntime {
  readonly compare: boolean
  update(input: HeatmapRuntimeInput): void
  resize(): void
  dispose(): void
}

function regionForName(name: string): MuscleRegion | null {
  return REGION_SET.has(name) ? (name as MuscleRegion) : null
}

function buildInstance(THREE: ThreeModule, source: import("three").Group): InstanceRuntime {
  const root = source.clone(true)
  const meshes = new Map<MuscleRegion, import("three").Mesh>()
  const materials = new Map<MuscleRegion, import("three").MeshStandardMaterial>()
  const regionsByObjectId = new Map<string, MuscleRegion>()

  root.traverse((object) => {
    const mesh = object as import("three").Mesh
    if (!mesh.isMesh) return
    const region = regionForName(mesh.name)
    if (!region) return

    const sourceMaterial = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material
    const material = (sourceMaterial as import("three").MeshStandardMaterial).clone()
    material.emissive.setRGB(0, 0, 0)
    material.emissiveIntensity = 0
    mesh.material = material

    meshes.set(region, mesh)
    materials.set(region, material)
    regionsByObjectId.set(mesh.uuid, region)
  })

  const scene = new THREE.Scene()
  scene.add(root)
  scene.add(new THREE.AmbientLight(0xffffff, 1.15))

  const keyLight = new THREE.DirectionalLight(0xffffff, 2.2)
  keyLight.position.set(3, 5, 4)
  scene.add(keyLight)

  const fillLight = new THREE.DirectionalLight(0x9ab8ff, 0.75)
  fillLight.position.set(-4, 2, -3)
  scene.add(fillLight)

  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 60)
  return { scene, camera, meshes, materials, regionsByObjectId }
}

function applyScene(instance: InstanceRuntime, scene: HeatmapScene): void {
  for (const [region, material] of instance.materials) {
    const visual = scene.byRegion[region]
    applyVisualToMaterial(material, visual)
    if (visual.evaluated) {
      material.color.setRGB(0.2, 0.21, 0.24)
      material.roughness = 0.55
    } else {
      // 未评估：中性灰的漫反射，配合极低发光，绝不会被读成 0 分暗红。
      material.color.setRGB(0.42, 0.42, 0.46)
      material.roughness = 0.9
    }
  }
}

/**
 * Create the full runtime: probe already passed, three + GLTFLoader imported
 * dynamically, the GLB fetched (cached) and parsed. Throws on any failure so
 * the component can render the visible fallback + retry button.
 */
export async function createMuscleHeatmapRuntime(
  container: HTMLElement,
  initial: HeatmapRuntimeInput,
  options: HeatmapRuntimeOptions = {},
): Promise<HeatmapRuntime> {
  const [THREE, { GLTFLoader }] = await Promise.all([
    import("three"),
    import("three/examples/jsm/loaders/GLTFLoader.js"),
  ])
  let binary: ArrayBuffer
  try {
    binary = await withTimeout(
      loadMuscleBodyBinary(),
      MODEL_LOAD_TIMEOUT_MS,
      "3D 模型加载超时",
    )
  } catch (error) {
    // A timed-out fetch may still be in flight; drop the cache so the user's
    // explicit retry starts a fresh request instead of waiting on the old one.
    resetMuscleBodyCache()
    throw error
  }
  const gltf = await new GLTFLoader().parseAsync(binary, "")

  const source = gltf.scene
  const hasCompare = initial.compareScene !== null
  const after = buildInstance(THREE, source)
  const before = modelInstanceCount(hasCompare) === MAX_MODEL_INSTANCES
    ? buildInstance(THREE, source)
    : null

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0x000000, 0)
  renderer.domElement.style.display = "block"
  renderer.domElement.style.width = "100%"
  renderer.domElement.style.height = "100%"
  renderer.domElement.style.cursor = "grab"
  renderer.domElement.style.touchAction = "none"
  renderer.domElement.tabIndex = 0
  renderer.domElement.setAttribute("role", "img")
  container.append(renderer.domElement)
  const canvas = renderer.domElement

  const orbit: OrbitState = { distance: DEFAULT_DISTANCE, polar: DEFAULT_POLAR_ANGLE }
  let yaw = 0
  let disposed = false
  let selectionOutline: import("three").BoxHelper | null = null
  let annotationOutline: import("three").BoxHelper | null = null
  let annotationRegion: MuscleRegion | null = null

  const disposeOutline = (outline: import("three").BoxHelper | null) => {
    if (!outline) return
    outline.removeFromParent()
    outline.geometry.dispose()
    outline.material.dispose()
  }

  const wrapAngle = (angle: number) => {
    const full = Math.PI * 2
    return ((((angle + Math.PI) % full) + full) % full) - Math.PI
  }

  const aimCamera = (camera: import("three").PerspectiveCamera, aspect: number) => {
    camera.aspect = aspect > 0 ? aspect : 1
    const sinPolar = Math.sin(orbit.polar)
    camera.position.set(
      Math.sin(yaw) * sinPolar * orbit.distance,
      CAMERA_TARGET_Y + Math.cos(orbit.polar) * orbit.distance,
      Math.cos(yaw) * sinPolar * orbit.distance,
    )
    camera.lookAt(0, CAMERA_TARGET_Y, 0)
    camera.updateProjectionMatrix()
  }

  const render = () => {
    if (disposed) return
    const width = Math.max(1, container.clientWidth)
    const height = Math.max(1, container.clientHeight)
    const layout = layoutForWidth(width)

    renderer.setScissorTest(hasCompare)
    if (!hasCompare) {
      renderer.setViewport(0, 0, width, height)
      renderer.setScissor(0, 0, width, height)
      aimCamera(after.camera, width / height)
      renderer.render(after.scene, after.camera)
      return
    }

    if (layout === "split") {
      const half = width / 2
      if (before) {
        renderer.setViewport(0, 0, half, height)
        renderer.setScissor(0, 0, half, height)
        aimCamera(before.camera, half / height)
        renderer.render(before.scene, before.camera)
      }
      renderer.setViewport(half, 0, half, height)
      renderer.setScissor(half, 0, half, height)
      aimCamera(after.camera, half / height)
      renderer.render(after.scene, after.camera)
      return
    }

    const half = height / 2
    if (before) {
      renderer.setViewport(0, half, width, half)
      renderer.setScissor(0, half, width, half)
      aimCamera(before.camera, width / half)
      renderer.render(before.scene, before.camera)
    }
    renderer.setViewport(0, 0, width, half)
    renderer.setScissor(0, 0, width, half)
    aimCamera(after.camera, width / half)
    renderer.render(after.scene, after.camera)
  }

  const resize = () => {
    if (disposed) return
    renderer.setSize(
      Math.max(1, container.clientWidth),
      Math.max(1, container.clientHeight),
      false,
    )
    render()
  }

  const setAnnotation = (region: MuscleRegion | null) => {
    if (annotationRegion === region && annotationOutline) return
    disposeOutline(annotationOutline)
    annotationOutline = null
    annotationRegion = region
    if (!region || !before) return
    const mesh = after.meshes.get(region)
    if (!mesh) return
    annotationOutline = new THREE.BoxHelper(mesh, 0xffb347)
    annotationOutline.update()
    after.scene.add(annotationOutline)
  }

  const select = (region: MuscleRegion | null) => {
    disposeOutline(selectionOutline)
    selectionOutline = null
    if (region) {
      const mesh = after.meshes.get(region)
      if (mesh) {
        selectionOutline = new THREE.BoxHelper(mesh, 0xf7f7f2)
        selectionOutline.update()
        after.scene.add(selectionOutline)
      }
    }
    options.onSelect?.(region)
    render()
  }

  const raycaster = new THREE.Raycaster()

  const pick = (clientX: number, clientY: number) => {
    const rect = canvas.getBoundingClientRect()
    const width = rect.width || container.clientWidth || 1
    const height = rect.height || container.clientHeight || 1
    const layout = layoutForWidth(width)
    let instance = after
    let localX = clientX - rect.left
    let localY = clientY - rect.top
    let viewportWidth = width
    let viewportHeight = height

    if (before) {
      if (layout === "split") {
        viewportWidth = width / 2
        if (localX >= viewportWidth) {
          instance = after
          localX -= viewportWidth
        } else {
          instance = before
        }
      } else {
        viewportHeight = height / 2
        if (localY >= viewportHeight) {
          instance = after
          localY -= viewportHeight
        } else {
          instance = before
        }
      }
    }

    const pointer = new THREE.Vector2(
      (localX / viewportWidth) * 2 - 1,
      -(localY / viewportHeight) * 2 + 1,
    )
    raycaster.setFromCamera(pointer, instance.camera)
    const hits = raycaster.intersectObjects([...instance.meshes.values()], false)
    if (hits.length === 0) {
      select(null)
      return
    }
    const region =
      instance.regionsByObjectId.get(hits[0].object.uuid)
      ?? regionForName(hits[0].object.name)
    select(region)
  }

  let dragging = false
  let pointerId = -1
  let lastX = 0
  let lastY = 0
  let travel = 0

  const onPointerDown = (event: PointerEvent) => {
    dragging = true
    pointerId = event.pointerId
    lastX = event.clientX
    lastY = event.clientY
    travel = 0
    canvas.setPointerCapture?.(event.pointerId)
    canvas.style.cursor = "grabbing"
    canvas.focus({ preventScroll: true })
  }

  const onPointerMove = (event: PointerEvent) => {
    if (!dragging || event.pointerId !== pointerId) return
    const deltaX = event.clientX - lastX
    const deltaY = event.clientY - lastY
    lastX = event.clientX
    lastY = event.clientY
    travel += Math.abs(deltaX) + Math.abs(deltaY)
    yaw = wrapAngle(yaw - deltaX * 0.007)
    orbit.polar = clampOrbit({ ...orbit, polar: orbit.polar - deltaY * 0.006 }).polar
    render()
  }

  const endDrag = (event: PointerEvent, allowPick: boolean) => {
    if (!dragging) return
    dragging = false
    canvas.style.cursor = "grab"
    if (canvas.hasPointerCapture?.(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId)
    }
    if (allowPick && travel < 6) pick(event.clientX, event.clientY)
  }

  const onPointerUp = (event: PointerEvent) => endDrag(event, true)
  const onPointerCancel = (event: PointerEvent) => endDrag(event, false)

  const onWheel = (event: WheelEvent) => {
    event.preventDefault()
    const next = orbit.distance * Math.exp(event.deltaY * 0.0012)
    orbit.distance = clampOrbit({ ...orbit, distance: next }).distance
    render()
  }

  const onKeyDown = (event: KeyboardEvent) => {
    let handled = true
    switch (event.key) {
      case "ArrowLeft":
        yaw = wrapAngle(yaw - 0.1)
        break
      case "ArrowRight":
        yaw = wrapAngle(yaw + 0.1)
        break
      case "ArrowUp":
        orbit.polar = clampOrbit({ ...orbit, polar: orbit.polar - 0.08 }).polar
        break
      case "ArrowDown":
        orbit.polar = clampOrbit({ ...orbit, polar: orbit.polar + 0.08 }).polar
        break
      case "+":
      case "=":
        orbit.distance = clampOrbit({ ...orbit, distance: orbit.distance * 0.9 }).distance
        break
      case "-":
      case "_":
        orbit.distance = clampOrbit({ ...orbit, distance: orbit.distance * 1.1 }).distance
        break
      case "Escape":
        select(null)
        break
      default:
        handled = false
    }
    if (handled) {
      event.preventDefault()
      render()
    }
  }

  canvas.addEventListener("pointerdown", onPointerDown)
  canvas.addEventListener("pointermove", onPointerMove)
  canvas.addEventListener("pointerup", onPointerUp)
  canvas.addEventListener("pointercancel", onPointerCancel)
  canvas.addEventListener("wheel", onWheel, { passive: false })
  canvas.addEventListener("keydown", onKeyDown)

  const resizeObserver =
    typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => resize())
  resizeObserver?.observe(container)
  window.addEventListener("resize", resize)

  applyScene(after, initial.scene)
  if (before && initial.compareScene) applyScene(before, initial.compareScene)
  if (hasCompare) setAnnotation(initial.highlightRegion)
  canvas.setAttribute("aria-label", buildAriaSummary(initial.scene))
  resize()

  return {
    compare: hasCompare,
    update(next) {
      if (disposed) return
      if ((next.compareScene !== null) !== hasCompare) return
      applyScene(after, next.scene)
      if (before && next.compareScene) applyScene(before, next.compareScene)
      setAnnotation(hasCompare ? next.highlightRegion : null)
      canvas.setAttribute("aria-label", buildAriaSummary(next.scene))
      render()
    },
    resize,
    dispose() {
      if (disposed) return
      disposed = true
      resizeObserver?.disconnect()
      window.removeEventListener("resize", resize)
      canvas.removeEventListener("pointerdown", onPointerDown)
      canvas.removeEventListener("pointermove", onPointerMove)
      canvas.removeEventListener("pointerup", onPointerUp)
      canvas.removeEventListener("pointercancel", onPointerCancel)
      canvas.removeEventListener("wheel", onWheel)
      canvas.removeEventListener("keydown", onKeyDown)
      disposeOutline(selectionOutline)
      disposeOutline(annotationOutline)
      selectionOutline = null
      annotationOutline = null
      for (const instance of [before, after]) {
        if (!instance) continue
        for (const material of instance.materials.values()) material.dispose()
      }
      const geometries = new Set<import("three").BufferGeometry>()
      source.traverse((object) => {
        const mesh = object as import("three").Mesh
        if (!mesh.isMesh) return
        geometries.add(mesh.geometry)
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
        for (const material of materials) material.dispose()
      })
      for (const geometry of geometries) geometry.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      canvas.remove()
    },
  }
}
