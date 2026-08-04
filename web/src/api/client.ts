/* HTTP 客户端封装：axios 实例 + 拦截器 + SSE 流处理 */
import axios from "axios"
import type { CoachAnimatedTTSResponse, CoachTTSStatusResponse } from "./types"

const client = axios.create({
  baseURL: "",
  headers: { "Content-Type": "application/json" },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const detail = err.response?.data?.detail
    const msg = typeof detail === "string"
      ? detail
      : detail?.message || err.message || "请求失败"
    return Promise.reject(new Error(msg))
  },
)

export default client

/** SSE 流式读取，逐段回调 */
export async function streamFetch(
  url: string,
  body: unknown,
  onChunk: (text: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
) {
  const token = localStorage.getItem("token")
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })

  if (!resp.ok || !resp.body) {
    throw new Error(`Stream request failed: ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6)
        if (data === "[DONE]") {
          onDone()
          return
        }
        onChunk(data)
      }
    }
  }
  onDone()
}

/** Fetch coach TTS status without relying on axios JSON helpers. */
export async function fetchCoachTTSStatus(): Promise<CoachTTSStatusResponse> {
  const token = localStorage.getItem("token")
  const response = await fetch("/api/coach/tts/status", {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!response.ok) {
    throw new Error(`TTS status failed: ${response.status}`)
  }
  return response.json() as Promise<CoachTTSStatusResponse>
}

/** Fetch synthesized WAV and its complete mouth-cue timeline as one payload. */
export async function fetchCoachAnimatedTTSPayload(
  text: string,
  signal?: AbortSignal,
): Promise<CoachAnimatedTTSResponse> {
  const token = localStorage.getItem("token")
  const response = await fetch("/api/coach/tts/animated", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text }),
    signal,
  })
  if (!response.ok) {
    throw new Error(response.status === 503 ? "语音暂不可用" : `Animated TTS request failed: ${response.status}`)
  }
  const payload = await response.json() as CoachAnimatedTTSResponse
  if (payload.mime_type !== "audio/wav" || !payload.audio_base64) {
    throw new Error("Unexpected animated TTS payload")
  }
  return payload
}

/** Download synthesized coach speech as a WAV blob. */
export async function fetchCoachTTSBlob(text: string): Promise<Blob> {
  const token = localStorage.getItem("token")
  const response = await fetch("/api/coach/tts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) {
    throw new Error(response.status === 503 ? "语音暂不可用" : `TTS request failed: ${response.status}`)
  }
  const contentType = response.headers.get("content-type") || ""
  if (!contentType.includes("audio/wav") && !contentType.includes("audio/")) {
    throw new Error("Unexpected TTS content type")
  }
  return response.blob()
}
