/* Synchronize one active coach message with decoded audio, visemes, and analyser energy. */
import { useCallback, useEffect, useRef, useState } from "react"
import { fetchCoachAnimatedTTS } from "@/api"
import { truncateForTTS } from "@/components/coach-audio"
import { mouthOpenFromFrequencyData } from "@/components/coach-animation"
import {
  audioBlobFromBase64,
  CoachVisemeClock,
  fallbackVisemeFromEnergy,
  type CoachMouthCue,
  type CoachViseme,
} from "@/components/coach-lip-sync"

export type CoachVoiceStatus = "idle" | "loading" | "playing" | "paused" | "error"
export type CoachVoiceAlignment = "rhubarb" | "energy" | null

interface CoachVoiceState {
  activeId: string | null
  status: CoachVoiceStatus
  error: string | null
  analyser: AnalyserNode | null
  viseme: CoachViseme
  alignment: CoachVoiceAlignment
}

interface CachedAnimatedSpeech {
  objectUrl: string
  mouthCues: CoachMouthCue[]
  alignment: Exclude<CoachVoiceAlignment, null>
}

const INITIAL_STATE: CoachVoiceState = {
  activeId: null,
  status: "idle",
  error: null,
  analyser: null,
  viseme: "X",
  alignment: null,
}

// Coordinate browser audio setup, playback cancellation, and cue-boundary state updates.
export function useCoachVoice() {
  const [state, setState] = useState<CoachVoiceState>(INITIAL_STATE)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null)
  const speechCacheRef = useRef<Map<string, CachedAnimatedSpeech>>(new Map())
  const requestAbortRef = useRef<AbortController | null>(null)
  const mediaCleanupRef = useRef<(() => void) | null>(null)
  const activeIdRef = useRef<string | null>(null)
  const playbackRequestRef = useRef(0)
  const animationFrameRef = useRef(0)
  const visemeClockRef = useRef(new CoachVisemeClock())
  const visemeRef = useRef<CoachViseme>("X")
  const mountedRef = useRef(true)

  const setViseme = useCallback((viseme: CoachViseme) => {
    if (visemeRef.current === viseme) return
    visemeRef.current = viseme
    if (!mountedRef.current) return
    setState((current) => ({ ...current, viseme }))
  }, [])

  const resetViseme = useCallback(() => {
    window.cancelAnimationFrame(animationFrameRef.current)
    animationFrameRef.current = 0
    visemeClockRef.current.reset()
    setViseme("X")
  }, [setViseme])

  // Abort network work that no longer belongs to the selected coach message.
  const abortPendingRequest = useCallback(() => {
    requestAbortRef.current?.abort()
    requestAbortRef.current = null
  }, [])

  // Pre-unlock the browser audio context while a trusted user gesture is active.
  const prepare = useCallback(() => {
    if (!mountedRef.current) return
    try {
      const AudioContextCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) return
      if (!contextRef.current) contextRef.current = new AudioContextCtor()
      if (contextRef.current.state === "suspended") {
        void contextRef.current.resume().catch(() => undefined)
      }
    } catch {
      // Playback reports a local voice error if audio setup still fails later.
    }
  }, [])

  const ensureGraph = useCallback((audio: HTMLAudioElement) => {
    const AudioContextCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextCtor) throw new Error("Web Audio is unavailable in this browser")
    if (!contextRef.current) contextRef.current = new AudioContextCtor()
    if (!analyserRef.current) {
      const analyser = contextRef.current.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.72
      analyserRef.current = analyser
    }
    if (!sourceRef.current) {
      const source = contextRef.current.createMediaElementSource(audio)
      source.connect(analyserRef.current)
      analyserRef.current.connect(contextRef.current.destination)
      sourceRef.current = source
    }
    return { context: contextRef.current, analyser: analyserRef.current }
  }, [])

  const stopCurrent = useCallback(() => {
    resetViseme()
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
  }, [resetViseme])

  const pause = useCallback(() => {
    playbackRequestRef.current += 1
    abortPendingRequest()
    stopCurrent()
    if (!mountedRef.current) return
    setState((current) => ({
      ...current,
      status: current.activeId ? "paused" : "idle",
      error: null,
      viseme: "X",
    }))
  }, [abortPendingRequest, stopCurrent])

  const startVisemeClock = useCallback((
    audio: HTMLAudioElement,
    mouthCues: CoachMouthCue[],
    alignment: Exclude<CoachVoiceAlignment, null>,
  ) => {
    resetViseme()
    visemeClockRef.current.setCues(mouthCues)
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return
    let frequency = new Uint8Array(analyserRef.current?.frequencyBinCount ?? 128)

    const update = () => {
      if (!mountedRef.current || audio.paused || audio.ended) return
      let nextViseme: CoachViseme
      if (alignment === "rhubarb") {
        nextViseme = visemeClockRef.current.update(audio.currentTime)
      } else {
        const analyser = analyserRef.current
        if (analyser && frequency.length !== analyser.frequencyBinCount) {
          frequency = new Uint8Array(analyser.frequencyBinCount)
        }
        if (analyser) analyser.getByteFrequencyData(frequency)
        nextViseme = fallbackVisemeFromEnergy(mouthOpenFromFrequencyData(frequency))
      }
      setViseme(nextViseme)
      animationFrameRef.current = window.requestAnimationFrame(update)
    }
    update()
  }, [resetViseme, setViseme])

  const play = useCallback(async (id: string, text: string) => {
    if (!mountedRef.current) return
    const utterance = truncateForTTS(text)
    if (!utterance) return
    if (activeIdRef.current === id && audioRef.current && !audioRef.current.paused) {
      pause()
      return
    }

    const requestId = ++playbackRequestRef.current
    abortPendingRequest()
    stopCurrent()
    visemeRef.current = "X"
    setState({
      activeId: id,
      status: "loading",
      error: null,
      analyser: analyserRef.current,
      viseme: "X",
      alignment: null,
    })
    activeIdRef.current = id

    try {
      let cached = speechCacheRef.current.get(id)
      if (!cached) {
        const controller = new AbortController()
        requestAbortRef.current = controller
        let payload
        try {
          payload = await fetchCoachAnimatedTTS(utterance, controller.signal)
        } finally {
          if (requestAbortRef.current === controller) requestAbortRef.current = null
        }
        if (!mountedRef.current || requestId !== playbackRequestRef.current) return
        const blob = audioBlobFromBase64(payload.audio_base64, payload.mime_type)
        cached = {
          objectUrl: URL.createObjectURL(blob),
          mouthCues: payload.mouth_cues,
          alignment: payload.alignment,
        }
        speechCacheRef.current.set(id, cached)
      }
      if (!mountedRef.current || requestId !== playbackRequestRef.current) return

      if (!audioRef.current) {
        audioRef.current = new Audio()
        audioRef.current.preload = "auto"
        const handlePause = () => {
          resetViseme()
          if (!mountedRef.current) return
          setState((current) => ({
            ...current,
            status: current.status === "playing" ? "paused" : current.status,
            viseme: "X",
          }))
        }
        const handleEnded = () => {
          resetViseme()
          if (!mountedRef.current) return
          setState((current) => ({
            ...current,
            status: "idle",
            activeId: null,
            error: null,
            viseme: "X",
          }))
          activeIdRef.current = null
        }
        const handleError = () => {
          playbackRequestRef.current += 1
          abortPendingRequest()
          resetViseme()
          if (!mountedRef.current) return
          setState((current) => ({
            ...current,
            status: "error",
            error: "语音暂不可用",
            viseme: "X",
            alignment: null,
          }))
        }
        audioRef.current.addEventListener("pause", handlePause)
        audioRef.current.addEventListener("ended", handleEnded)
        audioRef.current.addEventListener("error", handleError)
        mediaCleanupRef.current = () => {
          audioRef.current?.removeEventListener("pause", handlePause)
          audioRef.current?.removeEventListener("ended", handleEnded)
          audioRef.current?.removeEventListener("error", handleError)
        }
      }

      const audio = audioRef.current
      audio.src = cached.objectUrl
      audio.currentTime = 0
      const { context, analyser } = ensureGraph(audio)
      if (context.state === "suspended") await context.resume()
      if (!mountedRef.current || requestId !== playbackRequestRef.current) return
      await audio.play()
      if (!mountedRef.current || requestId !== playbackRequestRef.current) {
        audio.pause()
        return
      }
      setState({
        activeId: id,
        status: "playing",
        error: null,
        analyser,
        viseme: "X",
        alignment: cached.alignment,
      })
      startVisemeClock(audio, cached.mouthCues, cached.alignment)
    } catch (error) {
      if (!mountedRef.current || requestId !== playbackRequestRef.current) return
      resetViseme()
      const message = error instanceof Error ? error.message : "语音暂不可用"
      setState({
        activeId: id,
        status: "error",
        error: message.includes("语音") ? message : "语音暂不可用",
        analyser: analyserRef.current,
        viseme: "X",
        alignment: null,
      })
    }
  }, [abortPendingRequest, ensureGraph, pause, resetViseme, startVisemeClock, stopCurrent])

  useEffect(() => {
    mountedRef.current = true
    const speechCache = speechCacheRef.current
    return () => {
      mountedRef.current = false
      playbackRequestRef.current += 1
      abortPendingRequest()
      stopCurrent()
      mediaCleanupRef.current?.()
      mediaCleanupRef.current = null
      speechCache.forEach(({ objectUrl }) => URL.revokeObjectURL(objectUrl))
      speechCache.clear()
      void contextRef.current?.close()
      contextRef.current = null
      analyserRef.current = null
      sourceRef.current = null
      audioRef.current = null
    }
  }, [abortPendingRequest, stopCurrent])

  return {
    activeId: state.activeId,
    status: state.status,
    error: state.error,
    analyser: state.analyser,
    viseme: state.viseme,
    alignment: state.alignment,
    prepare,
    play,
    pause,
  }
}
