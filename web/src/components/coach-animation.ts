/* Convert live voice analyser data into a normalized fallback mouth signal. */

// Average the useful speech-frequency bins after applying a small noise gate.
export function mouthOpenFromFrequencyData(data: Uint8Array): number {
  if (data.length === 0) return 0
  const usefulBins = Math.max(1, Math.floor(data.length * 0.38))
  let energy = 0
  for (let index = 0; index < usefulBins; index += 1) {
    energy += data[index] ?? 0
  }
  const average = energy / usefulBins
  const noiseGate = 12
  if (average <= noiseGate) return 0
  return Math.min(1, (average - noiseGate) / 170)
}
