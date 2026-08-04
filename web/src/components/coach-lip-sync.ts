/* Provide validated viseme timing, analyser fallback, and audio payload decoding. */

export type CoachViseme = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "X"

export interface CoachMouthCue {
  start: number
  end: number
  value: CoachViseme
}

const COACH_VISEMES = new Set<CoachViseme>(["A", "B", "C", "D", "E", "F", "G", "H", "X"])

// Resolve a timestamp to one mouth shape while treating all gaps as rest.
export function visemeAtTime(cues: readonly CoachMouthCue[], currentTime: number): CoachViseme {
  if (!Number.isFinite(currentTime) || currentTime < 0) return "X"
  let low = 0
  let high = cues.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const cue = cues[middle]
    if (!cue) break
    if (currentTime < cue.start) {
      high = middle - 1
    } else if (currentTime >= cue.end) {
      low = middle + 1
    } else {
      return cue.value
    }
  }
  return "X"
}

// Convert normalized analyser energy into the four-shape offline fallback.
export function fallbackVisemeFromEnergy(energy: number): CoachViseme {
  const normalized = Math.min(1, Math.max(0, Number.isFinite(energy) ? energy : 0))
  if (normalized < 0.08) return "X"
  if (normalized < 0.36) return "B"
  if (normalized < 0.7) return "C"
  return "D"
}

// Decode base64 audio only after the complete animated response is available.
export function audioBlobFromBase64(encoded: string, mimeType: string): Blob {
  const binary = atob(encoded)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new Blob([bytes], { type: mimeType })
}

// Validate API mouth cues before they can drive the layered portrait.
export function validateMouthCues(cues: readonly CoachMouthCue[]): CoachMouthCue[] {
  let previousEnd = 0
  return cues.map((cue, index) => {
    if (
      !Number.isFinite(cue.start)
      || !Number.isFinite(cue.end)
      || cue.start < 0
      || cue.end <= cue.start
      || cue.start < previousEnd
      || !COACH_VISEMES.has(cue.value)
    ) {
      throw new Error(`Invalid mouth cue at index ${index}`)
    }
    previousEnd = cue.end
    return { ...cue }
  })
}

// Track one cue sequence across pause, replay, and message replacement.
export class CoachVisemeClock {
  private cues: CoachMouthCue[] = []
  current: CoachViseme = "X"

  constructor(cues: readonly CoachMouthCue[] = []) {
    this.setCues(cues)
  }

  setCues(cues: readonly CoachMouthCue[]): CoachViseme {
    this.cues = validateMouthCues(cues)
    return this.reset()
  }

  update(currentTime: number): CoachViseme {
    this.current = visemeAtTime(this.cues, currentTime)
    return this.current
  }

  reset(): CoachViseme {
    this.current = "X"
    return this.current
  }
}
