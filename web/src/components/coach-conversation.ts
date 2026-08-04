/* Pure conversation helpers shared by browser speech input and its tests. */
import type { DigitalCoachState } from "@/components/digital-coach"
import type { CoachVoiceStatus } from "@/hooks/use-coach-voice"

export type CoachConversationStatus = "idle" | "thinking" | "error"

export interface SpeechResultLike {
  0?: { transcript: string }
}

// Resolve concurrent chat, speech-input, and playback activity to one character state.
export function resolveCoachPresentationState(
  conversationStatus: CoachConversationStatus,
  listening: boolean,
  voiceStatus: CoachVoiceStatus,
): DigitalCoachState {
  if (listening) return "listening"
  if (voiceStatus === "playing") return "speaking"
  if (conversationStatus === "thinking" || voiceStatus === "loading") return "thinking"
  if (conversationStatus === "error") return "error"
  return "idle"
}

// Rebuild the full cumulative transcript emitted by the Web Speech API.
export function transcriptFromSpeechResults(results: ArrayLike<SpeechResultLike>) {
  let transcript = ""
  for (let index = 0; index < results.length; index += 1) {
    transcript += results[index]?.[0]?.transcript ?? ""
  }
  return transcript.trim()
}
