#!/usr/bin/env node
/* Deterministic hand-built humanoid for the 3D muscle heatmap.
 *
 * The asset contract is owned by web/src/muscle-heatmap.ts: the GLB must contain
 * exactly the twelve muscle region meshes and nothing else. We build it from box
 * primitives with a zero-dependency writer so the committed bytes can be
 * reproduced by `node scripts/generate-muscle-body-glb.mjs` at any time.
 *
 * Export `buildMuscleBodyGlb()` so the vitest asset check can assert the
 * committed file byte-for-byte.
 */
import { mkdir, writeFile } from "node:fs/promises"
import { dirname } from "node:path"
import { fileURLToPath, pathToFileURL } from "node:url"

export const MUSCLE_REGION_NAMES = [
  "chest",
  "upper_back",
  "lower_back",
  "abs",
  "traps",
  "shoulders",
  "arms",
  "forearms",
  "glutes",
  "quads",
  "hamstrings",
  "calves",
]

/** Six faces of a unit cube, counter-clockwise from outside (position, normal). */
const BOX_FACES = [
  { normal: [1, 0, 0], corners: [[1, -1, -1], [1, 1, -1], [1, 1, 1], [1, -1, 1]] },
  { normal: [-1, 0, 0], corners: [[-1, -1, 1], [-1, 1, 1], [-1, 1, -1], [-1, -1, -1]] },
  { normal: [0, 1, 0], corners: [[-1, 1, 1], [1, 1, 1], [1, 1, -1], [-1, 1, -1]] },
  { normal: [0, -1, 0], corners: [[-1, -1, -1], [1, -1, -1], [1, -1, 1], [-1, -1, 1]] },
  { normal: [0, 0, 1], corners: [[-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]] },
  { normal: [0, 0, -1], corners: [[1, -1, -1], [-1, -1, -1], [-1, 1, -1], [1, 1, -1]] },
]

const FACE_INDICES = [0, 1, 2, 0, 2, 3]

/**
 * Box primitives, in metres, feet resting on y = 0. Paired muscles use one
 * mesh made of two boxes (the renderer treats each name as one region).
 */
const BODY_REGIONS = {
  chest: [{ x: 0, y: 1.58, z: 0.1, w: 0.46, h: 0.32, d: 0.2 }],
  upper_back: [{ x: 0, y: 1.6, z: -0.12, w: 0.46, h: 0.36, d: 0.16 }],
  lower_back: [{ x: 0, y: 1.3, z: -0.11, w: 0.34, h: 0.36, d: 0.14 }],
  abs: [{ x: 0, y: 1.3, z: 0.1, w: 0.34, h: 0.38, d: 0.16 }],
  traps: [{ x: 0, y: 1.82, z: 0, w: 0.56, h: 0.12, d: 0.26 }],
  shoulders: [
    { x: -0.3, y: 1.72, z: 0, w: 0.22, h: 0.22, d: 0.26 },
    { x: 0.3, y: 1.72, z: 0, w: 0.22, h: 0.22, d: 0.26 },
  ],
  arms: [
    { x: -0.34, y: 1.47, z: 0, w: 0.16, h: 0.34, d: 0.16 },
    { x: 0.34, y: 1.47, z: 0, w: 0.16, h: 0.34, d: 0.16 },
  ],
  forearms: [
    { x: -0.35, y: 1.17, z: 0.015, w: 0.14, h: 0.3, d: 0.14 },
    { x: 0.35, y: 1.17, z: 0.015, w: 0.14, h: 0.3, d: 0.14 },
  ],
  glutes: [
    { x: -0.12, y: 1.1, z: -0.08, w: 0.22, h: 0.22, d: 0.2 },
    { x: 0.12, y: 1.1, z: -0.08, w: 0.22, h: 0.22, d: 0.2 },
  ],
  quads: [
    { x: -0.13, y: 0.82, z: 0.03, w: 0.2, h: 0.5, d: 0.2 },
    { x: 0.13, y: 0.82, z: 0.03, w: 0.2, h: 0.5, d: 0.2 },
  ],
  hamstrings: [
    { x: -0.13, y: 0.82, z: -0.1, w: 0.18, h: 0.46, d: 0.12 },
    { x: 0.13, y: 0.82, z: -0.1, w: 0.18, h: 0.46, d: 0.12 },
  ],
  calves: [
    { x: -0.12, y: 0.27, z: 0, w: 0.16, h: 0.52, d: 0.16 },
    { x: 0.12, y: 0.27, z: 0, w: 0.16, h: 0.52, d: 0.16 },
  ],
}

const GLB_MAGIC = 0x46546c67
const JSON_CHUNK = 0x4e4f534a
const BIN_CHUNK = 0x004e4942
const ARRAY_BUFFER = 34962
const ELEMENT_ARRAY_BUFFER = 34963
const FLOAT = 5126
const UNSIGNED_SHORT = 5123

function align4(value) {
  return (value + 3) & ~3
}

function buildRegionGeometry(boxes) {
  const positions = []
  const normals = []
  const indices = []

  for (const box of boxes) {
    const vertexOffset = positions.length / 3
    BOX_FACES.forEach((face, faceIndex) => {
      for (const corner of face.corners) {
        positions.push(
          box.x + (box.w / 2) * corner[0],
          box.y + (box.h / 2) * corner[1],
          box.z + (box.d / 2) * corner[2],
        )
        normals.push(face.normal[0], face.normal[1], face.normal[2])
      }
      const base = vertexOffset + faceIndex * 4
      for (const index of FACE_INDICES) indices.push(base + index)
    })
  }

  return {
    positions: new Float32Array(positions),
    normals: new Float32Array(normals),
    indices: new Uint16Array(indices),
  }
}

function boundsOf(positions) {
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[index + axis]
      if (value < min[axis]) min[axis] = value
      if (value > max[axis]) max[axis] = value
    }
  }
  return { min, max }
}

/** Build the complete GLB as a Buffer. Deterministic across runs and platforms. */
export function buildMuscleBodyGlb() {
  const chunks = []
  const bufferViews = []
  const accessors = []
  const meshes = []
  const materials = []
  let byteLength = 0

  const addView = (typedArray, target) => {
    const padding = align4(byteLength) - byteLength
    if (padding > 0) {
      chunks.push(Buffer.alloc(padding))
      byteLength += padding
    }
    const bytes = Buffer.from(typedArray.buffer, typedArray.byteOffset, typedArray.byteLength)
    const byteOffset = byteLength
    chunks.push(bytes)
    byteLength += bytes.byteLength
    bufferViews.push({ buffer: 0, byteOffset, byteLength: bytes.byteLength, target })
    return bufferViews.length - 1
  }

  for (const [regionIndex, region] of MUSCLE_REGION_NAMES.entries()) {
    const geometry = buildRegionGeometry(BODY_REGIONS[region])
    const { min, max } = boundsOf(geometry.positions)
    const positionView = addView(geometry.positions, ARRAY_BUFFER)
    const normalView = addView(geometry.normals, ARRAY_BUFFER)
    const indexView = addView(geometry.indices, ELEMENT_ARRAY_BUFFER)

    accessors.push(
      {
        bufferView: positionView,
        componentType: FLOAT,
        count: geometry.positions.length / 3,
        type: "VEC3",
        min,
        max,
      },
      {
        bufferView: normalView,
        componentType: FLOAT,
        count: geometry.normals.length / 3,
        type: "VEC3",
      },
      {
        bufferView: indexView,
        componentType: UNSIGNED_SHORT,
        count: geometry.indices.length,
        type: "SCALAR",
      },
    )

    const positionAccessor = regionIndex * 3
    const normalAccessor = regionIndex * 3 + 1
    const indexAccessor = regionIndex * 3 + 2

    meshes.push({
      name: region,
      primitives: [
        {
          attributes: { POSITION: positionAccessor, NORMAL: normalAccessor },
          indices: indexAccessor,
          material: regionIndex,
        },
      ],
    })

    materials.push({
      name: region,
      pbrMetallicRoughness: {
        baseColorFactor: [0.2, 0.21, 0.24, 1],
        metallicFactor: 0.05,
        roughnessFactor: 0.58,
      },
      emissiveFactor: [0, 0, 0],
    })
  }

  const binary = Buffer.concat(chunks)
  const gltf = {
    asset: { version: "2.0", generator: "lianleme-muscle-body-glb" },
    scene: 0,
    scenes: [{ name: "muscle-body", nodes: MUSCLE_REGION_NAMES.map((_, index) => index) }],
    nodes: MUSCLE_REGION_NAMES.map((name, index) => ({ name, mesh: index })),
    meshes,
    materials,
    accessors,
    bufferViews,
    buffers: [{ byteLength: binary.byteLength }],
  }

  let json = Buffer.from(JSON.stringify(gltf), "utf8")
  if (json.byteLength % 4 !== 0) {
    json = Buffer.concat([json, Buffer.alloc(align4(json.byteLength) - json.byteLength, 0x20)])
  }
  const binPadding = align4(binary.byteLength) - binary.byteLength
  const bin = binPadding > 0 ? Buffer.concat([binary, Buffer.alloc(binPadding)]) : binary

  const totalLength = 12 + 8 + json.byteLength + 8 + bin.byteLength
  const header = Buffer.alloc(12)
  header.writeUInt32LE(GLB_MAGIC, 0)
  header.writeUInt32LE(2, 4)
  header.writeUInt32LE(totalLength, 8)

  const jsonHeader = Buffer.alloc(8)
  jsonHeader.writeUInt32LE(json.byteLength, 0)
  jsonHeader.writeUInt32LE(JSON_CHUNK, 4)

  const binHeader = Buffer.alloc(8)
  binHeader.writeUInt32LE(bin.byteLength, 0)
  binHeader.writeUInt32LE(BIN_CHUNK, 4)

  return Buffer.concat([header, jsonHeader, json, binHeader, bin])
}

const DEFAULT_OUTPUT = fileURLToPath(new URL("../public/models/muscle-body.glb", import.meta.url))

const isMain =
  process.argv[1] !== undefined &&
  pathToFileURL(process.argv[1]).href === import.meta.url

if (isMain) {
  const glb = buildMuscleBodyGlb()
  await mkdir(dirname(DEFAULT_OUTPUT), { recursive: true })
  await writeFile(DEFAULT_OUTPUT, glb)
  console.log(`wrote ${DEFAULT_OUTPUT} (${glb.byteLength} bytes)`)
}
