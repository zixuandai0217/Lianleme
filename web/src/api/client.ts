/* HTTP 客户端封装：axios 实例 + 拦截器 + SSE 流处理 */
import axios from "axios"

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
    const msg = err.response?.data?.detail || err.message || "请求失败"
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
) {
  const token = localStorage.getItem("token")
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
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
