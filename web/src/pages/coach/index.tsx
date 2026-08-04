/* 2D digital coach page with streamed AI conversation, speech input, and voice playback. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Bot,
  ChevronRight,
  CircleStop,
  Dumbbell,
  Loader2,
  Mic,
  MicOff,
  RotateCcw,
  Send,
  UserRound,
  Volume2,
} from "lucide-react"
import { getChatHistory, getCoachTTSStatus, getTodayWorkout } from "@/api"
import { streamFetch } from "@/api/client"
import type { ChatMessageItem, TodayWorkout } from "@/api/types"
import {
  resolveCoachPresentationState,
  transcriptFromSpeechResults,
  type CoachConversationStatus,
  type SpeechResultLike,
} from "@/components/coach-conversation"
import { DigitalCoach, type DigitalCoachState } from "@/components/digital-coach"
import { VoiceMessageBubble } from "@/components/voice-message-bubble"
import { VoiceWaveform } from "@/components/voice-waveform"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useAuth } from "@/hooks/use-auth"
import { useCoachVoice } from "@/hooks/use-coach-voice"

interface DisplayMessage {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt?: string
  pending?: boolean
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechResultLike>
}

interface SpeechRecognitionErrorLike {
  error: string
}

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorLike) => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

const SUGGESTED_PROMPTS = [
  "根据今天的计划，帮我安排热身",
  "第一个动作应该注意什么？",
  "今天状态一般，训练怎么调整？",
  "给我一句开练前的提醒",
]

const STATUS_COPY: Record<DigitalCoachState, string> = {
  idle: "随时可以开始",
  listening: "正在听你说",
  thinking: "正在思考",
  speaking: "正在说话",
  error: "连接失败",
}

// Convert persisted API messages into stable local presentation records.
function toDisplayMessage(message: ChatMessageItem): DisplayMessage {
  return {
    id: `history-${message.id}`,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
  }
}

// Format compact transcript timestamps without exposing invalid dates.
function formatMessageTime(value?: string) {
  if (!value) return "刚刚"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "刚刚"
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

// Fetch persisted conversation and workout context without mutating React state.
async function fetchCoachContext(userId: number) {
  return Promise.allSettled([
    getChatHistory(userId, 40),
    getTodayWorkout(userId),
    getCoachTTSStatus(),
  ])
}

// Provide opt-in browser speech recognition and stream interim text into the composer.
function useSpeechInput(onTranscript: (text: string) => void) {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const supported = typeof window !== "undefined" && Boolean(
    window.SpeechRecognition || window.webkitSpeechRecognition,
  )

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const start = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) return

    const recognition = new SpeechRecognition()
    recognition.lang = "zh-CN"
    recognition.continuous = false
    recognition.interimResults = true
    recognitionRef.current = recognition
    setError(null)

    recognition.onresult = (event) => {
      const transcript = transcriptFromSpeechResults(event.results)
      if (transcript) onTranscript(transcript)
    }
    recognition.onerror = (event) => {
      if (event.error !== "aborted" && event.error !== "no-speech") {
        setError("没有听清，请再试一次")
      }
      setListening(false)
    }
    recognition.onend = () => {
      recognitionRef.current = null
      setListening(false)
    }

    try {
      recognition.start()
      setListening(true)
    } catch {
      recognitionRef.current = null
      setError("麦克风暂时不可用")
      setListening(false)
    }
  }, [onTranscript])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      recognitionRef.current = null
    }
  }, [])

  return { supported, listening, error, start, stop }
}

export default function CoachPage() {
  const { user } = useAuth()
  const voice = useCoachVoice()
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [workout, setWorkout] = useState<TodayWorkout | null>(null)
  const [input, setInput] = useState("")
  const [conversationStatus, setConversationStatus] = useState<CoachConversationStatus>("idle")
  const [historyLoading, setHistoryLoading] = useState(true)
  const [ttsAvailable, setTtsAvailable] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState("")
  const transcriptRef = useRef<HTMLDivElement>(null)
  const messageSequenceRef = useRef(0)
  const streamAbortRef = useRef<AbortController | null>(null)
  const speech = useSpeechInput(setInput)
  const userId = user?.id

  const firstExercise = workout?.exercises?.[0]
  const isBusy = historyLoading || conversationStatus === "thinking" || voice.status === "loading"
  const coachState = resolveCoachPresentationState(conversationStatus, speech.listening, voice.status)
  const statusCopy = voice.status === "loading"
    ? "正在准备语音与口型"
    : STATUS_COPY[coachState]

  const displayName = user?.nickname?.trim() || "训练伙伴"
  const workoutSummary = useMemo(() => {
    if (!workout) return "今日训练待安排"
    if (workout.is_rest_day) return "今天是恢复日"
    if (!workout.exercises?.length) return workout.message || "今日训练待安排"
    return `${workout.focus || "综合训练"} · ${workout.exercises.length} 个动作 · ${workout.estimated_duration || 0} 分钟`
  }, [workout])

  // Commit a completed context request to the conversation and workout surfaces.
  const applyCoachContext = useCallback(([
    historyResult,
    workoutResult,
    ttsResult,
  ]: Awaited<ReturnType<typeof fetchCoachContext>>) => {
    if (historyResult.status === "fulfilled") {
      setMessages(historyResult.value.messages.map(toDisplayMessage))
    } else {
      setPageError("对话记录暂时未能加载")
    }

    if (workoutResult.status === "fulfilled") {
      setWorkout(workoutResult.value)
    }
    setTtsAvailable(ttsResult.status === "fulfilled" && ttsResult.value.available)
    setHistoryLoading(false)
  }, [])

  // Load conversation memory and today's plan together after authentication resolves.
  const loadCoachContext = useCallback(async () => {
    if (!userId) return
    applyCoachContext(await fetchCoachContext(userId))
  }, [applyCoachContext, userId])

  useEffect(() => {
    if (!userId) return
    let active = true
    void fetchCoachContext(userId).then((result) => {
      if (active) applyCoachContext(result)
    })
    return () => {
      active = false
    }
  }, [applyCoachContext, userId])

  useEffect(() => {
    const viewport = transcriptRef.current
    if (!viewport) return
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    return () => streamAbortRef.current?.abort()
  }, [])

  // Send a user turn, stream the AI reply into one bubble, then speak the final text.
  const sendMessage = async (rawMessage: string) => {
    const message = rawMessage.trim()
    if (!message || !userId || isBusy) return

    if (ttsAvailable) voice.prepare()
    if (voice.status === "playing" || voice.status === "loading") voice.pause()
    speech.stop()
    setInput("")
    setPageError(null)
    setConversationStatus("thinking")

    const sequence = ++messageSequenceRef.current
    const userMessage: DisplayMessage = {
      id: `local-user-${sequence}`,
      role: "user",
      content: message,
    }
    const assistantId = `local-assistant-${sequence}`
    const assistantMessage: DisplayMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      pending: true,
    }
    setMessages((current) => [...current, userMessage, assistantMessage])

    streamAbortRef.current?.abort()
    const streamController = new AbortController()
    streamAbortRef.current = streamController
    let replyText = ""
    try {
      await streamFetch(
        "/api/coach/chat/stream",
        {
          user_id: userId,
          message,
          current_exercise: firstExercise?.name,
          completed_sets: 0,
          total_sets: firstExercise?.sets,
        },
        (chunk) => {
          if (streamController.signal.aborted) return
          replyText += chunk
          setMessages((current) => current.map((item) => (
            item.id === assistantId ? { ...item, content: replyText } : item
          )))
        },
        () => undefined,
        streamController.signal,
      )

      if (streamController.signal.aborted) return
      const finalReply = replyText.trim()
      const completedReply = finalReply || "我在，换个方式再问我一次。"
      setMessages((current) => current.map((item) => (
        item.id === assistantId
          ? { ...item, content: completedReply, pending: false }
          : item
      )))
      setConversationStatus("idle")
      setAnnouncement(`教练回复：${completedReply}`)
      if (finalReply && ttsAvailable) await voice.play(assistantId, finalReply)
    } catch (error) {
      if (streamController.signal.aborted || (error instanceof Error && error.name === "AbortError")) return
      const errorMessage = error instanceof Error ? error.message : "AI 教练暂时无法连接"
      setConversationStatus("error")
      setPageError(errorMessage)
      setAnnouncement("数字教练连接中断，请重新发送。")
      setMessages((current) => current.map((item) => (
        item.id === assistantId
          ? { ...item, content: "刚才的连接中断了，请重新发送。", pending: false }
          : item
      )))
    } finally {
      if (streamAbortRef.current === streamController) streamAbortRef.current = null
    }
  }

  // Submit the composer on Enter while preserving Shift+Enter for a new line.
  const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void sendMessage(input)
    }
  }

  return (
    <div className="-mx-4 -mt-5 overflow-hidden bg-[#fffdf9] sm:-mx-6 md:-mx-8 md:-mt-8 xl:-mx-10">
      <p className="sr-only" aria-live="polite">{announcement}</p>
      <header className="flex min-h-20 items-center justify-between gap-4 border-b border-[#e5e3de] px-4 py-4 sm:px-6 md:px-8 xl:px-10">
        <div className="min-w-0">
          <span className="block text-[0.66rem] font-bold uppercase text-[#a63d00] [letter-spacing:0.12em]">AI Coach / Live</span>
          <h1 className="mt-1 text-2xl font-semibold text-[#1d211f] sm:text-[1.75rem]">数字教练</h1>
        </div>
        <div className="flex min-w-0 items-center gap-2 text-right">
          <span className={`size-2 shrink-0 rounded-full ${coachState === "error" ? "bg-[#d83a2e]" : "bg-[#15966f]"}`} />
          <span className="truncate text-xs font-semibold text-[#535b56]">{displayName} · {workoutSummary}</span>
        </div>
      </header>

      <div className="grid min-h-[calc(100dvh-9rem)] lg:grid-cols-[minmax(0,1.12fr)_minmax(25rem,0.88fr)]">
        <section className="relative min-h-[31rem] overflow-hidden bg-[#151a16] lg:min-h-[calc(100dvh-9rem)]" aria-labelledby="coach-stage-title">
          <div className="absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-4 p-5 sm:p-7">
            <div>
              <p id="coach-stage-title" className="text-xs font-bold uppercase text-[#ff8a2a] [letter-spacing:0.12em]">POWER COACH / LIVE</p>
              <div className="mt-2 flex items-center gap-2">
                <span className={`size-2 rounded-full ${coachState === "listening" ? "bg-[#11a99a]" : coachState === "error" ? "bg-[#d83a2e]" : "bg-[#ff6a00]"}`} />
                <span className="text-sm font-semibold text-white" aria-live="polite">{statusCopy}</span>
              </div>
            </div>
            {(voice.status === "playing" || voice.status === "loading") && (
              <Tooltip>
                <TooltipTrigger
                  render={<Button type="button" variant="outline" size="icon" aria-label="停止教练语音" onClick={voice.pause} className="border-white/20 bg-[#151a16]/80 text-white hover:bg-[#242a25]" />}
                >
                  <CircleStop className="size-4" />
                </TooltipTrigger>
                <TooltipContent>停止语音</TooltipContent>
              </Tooltip>
            )}
          </div>

          <DigitalCoach
            ariaLabel={`原创卡通健身数字教练，当前状态：${statusCopy}`}
            state={coachState}
            variant="stage"
            viseme={voice.viseme}
            className="h-[31rem] lg:h-full lg:min-h-[calc(100dvh-9rem)]"
          />

          <div className="absolute inset-x-0 bottom-0 z-10 border-t border-white/12 bg-[#111511]/90 px-5 py-4 backdrop-blur-md sm:px-7">
            <div className="flex items-center gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-[#ff6a00] text-[#151a16]">
                <Dumbbell className="size-4" />
              </span>
              <div className="min-w-0">
                <p className="text-[0.65rem] font-bold uppercase text-white/55 [letter-spacing:0.1em]">当前训练</p>
                <p className="mt-0.5 truncate text-sm font-semibold text-white">
                  {firstExercise ? `${firstExercise.name} · ${firstExercise.sets} 组 × ${firstExercise.reps}` : workoutSummary}
                </p>
              </div>
              <VoiceWaveform
                analyser={voice.status === "playing" ? voice.analyser : null}
                active={voice.status === "playing"}
                barCount={20}
                className="ml-auto hidden h-8 w-36 sm:block md:w-44"
              />
            </div>
          </div>
        </section>

        <section className="flex min-h-[39rem] flex-col border-t border-[#e5e3de] bg-white lg:min-h-0 lg:border-t-0 lg:border-l" aria-labelledby="transcript-title">
          <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#eceae5] px-4 sm:px-6">
            <div>
              <h2 id="transcript-title" className="text-base font-semibold text-[#1d211f]">对话记录</h2>
              <p className="mt-0.5 text-xs text-[#626a65]">{messages.length ? `${messages.length} 条消息` : "新对话"}</p>
            </div>
            <Tooltip>
              <TooltipTrigger
                render={<Button type="button" variant="ghost" size="icon-sm" aria-label="刷新对话记录" onClick={() => {
                  setHistoryLoading(true)
                  setPageError(null)
                  void loadCoachContext()
                }} disabled={historyLoading || isBusy} />}
              >
                <RotateCcw className={`size-3.5 ${historyLoading ? "animate-spin" : ""}`} />
              </TooltipTrigger>
              <TooltipContent>刷新记录</TooltipContent>
            </Tooltip>
          </div>

          <div ref={transcriptRef} role="log" aria-live="off" className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-5 sm:px-6">
            {historyLoading && (
              <div className="grid min-h-48 place-items-center text-sm text-[#626a65]">
                <Loader2 className="size-5 animate-spin text-[#ff6a00]" />
              </div>
            )}

            {!historyLoading && messages.length === 0 && (
              <div className="mx-auto flex min-h-52 max-w-sm flex-col items-center justify-center text-center">
                <span className="grid size-12 place-items-center rounded-full bg-[#fff0e2] text-[#e95b00]">
                  <Bot className="size-5" />
                </span>
                <p className="mt-4 text-sm font-semibold text-[#1d211f]">{displayName}，我们开始吧</p>
                <p className="mt-1 text-sm leading-6 text-[#6b746e]">今天想先聊训练计划、动作细节，还是当前状态？</p>
              </div>
            )}

            <div className="space-y-5">
              {messages.map((message) => {
                const assistant = message.role === "assistant"
                return (
                  <article key={message.id} className={`flex gap-2.5 ${assistant ? "items-start" : "justify-end"}`}>
                    {assistant && (
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-[#1d211f] text-[#ff7a18]">
                        <Bot className="size-3.5" />
                      </span>
                    )}
                    <div className={`min-w-0 max-w-[86%] ${assistant ? "" : "text-right"}`}>
                      <div className={`inline-block rounded-md px-3.5 py-2.5 text-left text-sm leading-6 ${assistant ? "bg-[#f3f4f1] text-[#252a27]" : "bg-[#ff6a00] text-[#1d211f]"}`}>
                        {message.pending && !message.content ? (
                          <span className="inline-flex items-center gap-2 text-[#68716c]">
                            <Loader2 className="size-3.5 animate-spin" /> 正在思考
                          </span>
                        ) : message.content}
                      </div>
                      <div className={`mt-1.5 flex items-center gap-2 ${assistant ? "" : "justify-end"}`}>
                        {!assistant && <UserRound className="size-3 text-[#626a65]" />}
                        <span className="text-[0.65rem] text-[#626a65]">{formatMessageTime(message.createdAt)}</span>
                      </div>
                      {assistant && message.content && !message.pending && (
                        <div className="mt-2 max-w-sm">
                          <VoiceMessageBubble
                            messageId={message.id}
                            text={message.content}
                            available={ttsAvailable}
                            activeId={voice.activeId}
                            status={voice.status}
                            error={voice.error}
                            analyser={voice.analyser}
                            onPlay={(id, text) => {
                              voice.prepare()
                              void voice.play(id, text)
                            }}
                            onPause={voice.pause}
                          />
                        </div>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          </div>

          <div className="shrink-0 border-t border-[#eceae5] bg-[#fffdf9] p-4 sm:p-5">
            {pageError && <p className="mb-3 text-xs font-medium text-[#b83227]" role="alert">{pageError}</p>}
            {speech.error && <p className="mb-3 text-xs font-medium text-[#b83227]" role="alert">{speech.error}</p>}
            <div className="mb-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={isBusy}
                  onClick={() => void sendMessage(prompt)}
                  className="inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 rounded-md border border-[#dddcd7] bg-white px-2.5 text-xs font-medium text-[#454c48] transition-colors hover:border-[#ff6a00]/50 hover:bg-[#fff2e7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a00]/40 disabled:pointer-events-none disabled:opacity-50"
                >
                  {prompt}
                  <ChevronRight className="size-3" />
                </button>
              ))}
            </div>

            <div className="flex items-end gap-2 rounded-md border border-[#d9d8d3] bg-white p-2 shadow-[0_8px_30px_rgba(29,33,31,0.06)] focus-within:border-[#ff6a00] focus-within:ring-2 focus-within:ring-[#ff6a00]/12">
              <label htmlFor="coach-message" className="sr-only">发消息给数字教练</label>
              <textarea
                id="coach-message"
                value={input}
                rows={1}
                disabled={isBusy}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="问教练一个训练问题"
                className="max-h-28 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-[#1d211f] outline-none placeholder:text-[#9a9f9c] disabled:opacity-60"
              />

              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      variant={speech.listening ? "default" : "ghost"}
                      size="icon-lg"
                      aria-label={speech.listening ? "停止语音输入" : "开始语音输入"}
                      disabled={!speech.supported || isBusy}
                      onClick={speech.listening ? speech.stop : speech.start}
                      className={speech.listening ? "bg-[#11a99a] text-[#1d211f] hover:bg-[#0d8d81]" : "text-[#59615c]"}
                    />
                  }
                >
                  {speech.listening ? <MicOff className="size-4" /> : <Mic className="size-4" />}
                </TooltipTrigger>
                <TooltipContent>{speech.supported ? (speech.listening ? "停止收音" : "语音输入") : "浏览器不支持语音输入"}</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      size="icon-lg"
                      aria-label="发送消息"
                      disabled={!input.trim() || isBusy}
                      onClick={() => void sendMessage(input)}
                      className="bg-[#ff6a00] text-[#1d211f] hover:bg-[#e95b00]"
                    />
                  }
                >
                  {isBusy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                </TooltipTrigger>
                <TooltipContent>发送消息</TooltipContent>
              </Tooltip>
            </div>

            <div className="mt-2 flex items-center justify-between gap-3 text-[0.66rem] text-[#626a65]">
              <span className="truncate">{firstExercise ? `上下文：${firstExercise.name}` : "上下文：自由对话"}</span>
              <span className="flex shrink-0 items-center gap-1">
                 <Volume2 className="size-3" /> {ttsAvailable ? "AI 语音" : "语音未配置"}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
