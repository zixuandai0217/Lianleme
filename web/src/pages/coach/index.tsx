/* AI 陪练页：聊天界面 + SSE 流式消息 + DB 对话历史 */
import { useState, useRef, useEffect, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { MessageSquare, Send, Loader2, Bot, User } from "lucide-react"
import { streamFetch } from "@/api/client"
import { getChatHistory } from "@/api"
import { useAuth } from "@/hooks/use-auth"

interface Message {
  role: "user" | "assistant"
  content: string
  actions?: string[]
}

const WELCOME_MSG: Message = {
  role: "assistant",
  content: "你好！我是你的 AI 健身教练，准备好开始训练了吗？告诉我你今天想练什么，或者我们按计划来！",
  actions: ["按计划训练", "自由训练", "查看今日计划"],
}

export default function CoachPage() {
  const { userId } = useAuth()
  const [messages, setMessages] = useState<Message[]>([WELCOME_MSG])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const loadHistory = useCallback(async () => {
    if (!userId || historyLoaded) return
    try {
      const res = await getChatHistory(userId)
      if (res.messages.length > 0) {
        const loaded: Message[] = res.messages.map((m) => ({
          role: m.role,
          content: m.content,
        }))
        setMessages([WELCOME_MSG, ...loaded])
      }
    } catch {
      /* 静默，使用默认欢迎消息 */
    } finally {
      setHistoryLoaded(true)
    }
  }, [userId, historyLoaded])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  const sendMessage = async (text: string) => {
    if (!userId || !text.trim() || streaming) return
    const userMsg = text.trim()
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: userMsg }])
    setStreaming(true)

    let assistantContent = ""
    setMessages((prev) => [...prev, { role: "assistant", content: "" }])

    try {
      await streamFetch(
        "/api/coach/chat/stream",
        { user_id: userId, message: userMsg },
        (chunk) => {
          assistantContent += chunk
          setMessages((prev) => {
            const updated = [...prev]
            updated[updated.length - 1] = {
              role: "assistant",
              content: assistantContent,
            }
            return updated
          })
        },
        () => {
          setMessages((prev) => {
            const updated = [...prev]
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              actions: ["继续下一组", "换个动作", "结束训练"],
            }
            return updated
          })
        },
      )
    } catch {
      assistantContent = "抱歉，连接出现问题，请稍后再试。"
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: "assistant", content: assistantContent }
        return updated
      })
    } finally {
      setStreaming(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] md:h-[calc(100vh-4rem)]">
      <div className="mb-4">
        <h1 className="text-2xl font-bold tracking-tight">AI 陪练</h1>
        <p className="text-muted-foreground">你的专属 AI 健身教练，实时陪伴训练</p>
      </div>

      <Card className="flex-1 flex flex-col overflow-hidden min-h-0">
        <CardHeader className="pb-2 shrink-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageSquare className="h-4 w-4" />
            训练对话
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col overflow-hidden min-h-0 p-0">
          <div className="flex-1 overflow-y-auto px-4" ref={scrollRef}>
            <div className="space-y-4 py-4">
              {messages.map((msg, i) => (
                <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                  {msg.role === "assistant" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                  )}
                  <div
                    className={`max-w-[80%] space-y-2 ${
                      msg.role === "user" ? "order-first" : ""
                    }`}
                  >
                    <div
                      className={`rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                        msg.role === "user"
                          ? "bg-primary text-primary-foreground ml-auto"
                          : "bg-muted"
                      }`}
                    >
                      {msg.content || (streaming && i === messages.length - 1 && (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ))}
                    </div>
                    {msg.actions && msg.actions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {msg.actions.map((action) => (
                          <Badge
                            key={action}
                            variant="outline"
                            className="cursor-pointer hover:bg-accent transition-colors"
                            onClick={() => sendMessage(action)}
                          >
                            {action}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  {msg.role === "user" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Input area */}
          <div className="border-t p-4 shrink-0">
            <div className="flex gap-2">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                className="min-h-[44px] max-h-32 resize-none"
                rows={1}
              />
              <Button
                size="icon"
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || streaming}
                className="shrink-0"
              >
                {streaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
