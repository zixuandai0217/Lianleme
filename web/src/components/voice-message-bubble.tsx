/* Playable coach voice control with live waveform feedback. */
import { Loader2, Pause, Volume2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { VoiceWaveform } from "@/components/voice-waveform"
import type { CoachVoiceStatus } from "@/hooks/use-coach-voice"

interface VoiceMessageBubbleProps {
  messageId: string
  text: string
  available: boolean
  activeId: string | null
  status: CoachVoiceStatus
  error: string | null
  analyser: AnalyserNode | null
  onPlay: (id: string, text: string) => void
  onPause: () => void
}

export function VoiceMessageBubble({
  messageId,
  text,
  available,
  activeId,
  status,
  error,
  analyser,
  onPlay,
  onPause,
}: VoiceMessageBubbleProps) {
  const isActive = activeId === messageId
  const isLoading = isActive && status === "loading"
  const isPlaying = isActive && status === "playing"
  const showError = available && isActive && status === "error"

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex min-w-0 items-center gap-2 rounded-sm border border-border bg-card/80 px-2 py-1.5">
        <Button
          type="button"
          size="icon-sm"
          variant={isPlaying ? "default" : "outline"}
          aria-label={!available ? "教练语音未配置" : isPlaying ? "暂停教练语音" : "播放教练语音"}
          disabled={!available || !text.trim() || isLoading}
          onClick={() => {
            if (isPlaying) onPause()
            else void onPlay(messageId, text)
          }}
        >
          {isLoading ? <Loader2 className="size-3.5 animate-spin" /> : isPlaying ? <Pause className="size-3.5" /> : <Volume2 className="size-3.5" />}
        </Button>
        <VoiceWaveform analyser={isActive ? analyser : null} active={isPlaying} />
        <span className="font-sans text-[0.62rem] uppercase tracking-[0.12em] text-muted-foreground">
          {!available ? "语音未配置" : isLoading ? "合成中" : isPlaying ? "播放中" : "语音"}
        </span>
      </div>
      {showError && <p className="text-xs text-muted-foreground">{error || "语音暂不可用"}</p>}
    </div>
  )
}
