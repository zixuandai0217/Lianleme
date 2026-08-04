/* Pure coach-audio transforms shared by waveform, TTS, and unit tests. */

// Normalize analyser frequency bins into a symmetric mirrored bar array.
export function barsFromFrequencyData(
  data: Uint8Array,
  barCount: number,
  sensitivity = 1,
): number[] {
  const count = Math.max(2, barCount)
  if (data.length === 0) {
    return Array.from({ length: count }, () => 0.06)
  }

  const startBin = Math.floor(data.length * 0.05)
  const endBin = Math.floor(data.length * 0.4)
  const relevant = data.slice(startBin, endBin)
  const halfCount = Math.floor(count / 2)
  const bars: number[] = []
  let hasSignal = false
  const binPerBar = relevant.length / halfCount

  for (let index = 0; index < halfCount; index += 1) {
    const start = Math.floor(index * binPerBar)
    const end = Math.floor((index + 1) * binPerBar)
    let sum = 0
    for (let bin = start; bin < end; bin += 1) {
      sum += relevant[bin] ?? 0
    }
    const average = sum / Math.max(1, end - start)
    if (average > 4) hasSignal = true
    bars.push(Math.min(1, (average / 255) * sensitivity))
  }

  const mirrored = [...bars].reverse().concat(bars)
  if (!hasSignal) {
    return Array.from({ length: count }, () => 0.06)
  }
  return mirrored.map((value) => Math.max(0.04, Math.min(1, value)))
}

// Truncate coach reply text to the TTS request-body limit.
export function truncateForTTS(text: string, maxLength = 500): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxLength) return trimmed
  return trimmed.slice(0, maxLength)
}
