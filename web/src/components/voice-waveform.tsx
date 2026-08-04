/* Canvas equalizer bars inspired by symmetric mirror waveforms — low-freq focused, edge-faded. */
import { useEffect, useRef } from "react"
import { barsFromFrequencyData } from "@/components/coach-audio"

const DEFAULT_BAR_COUNT = 48

interface VoiceWaveformProps {
  analyser: AnalyserNode | null
  active: boolean
  barCount?: number
  sensitivity?: number
  className?: string
}

export function VoiceWaveform({
  analyser,
  active,
  barCount = DEFAULT_BAR_COUNT,
  sensitivity = 1.2,
  className = "",
}: VoiceWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const gradientCacheRef = useRef<CanvasGradient | null>(null)
  const lastWidthRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const reducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false
    const frequency = new Uint8Array(analyser?.frequencyBinCount ?? 32)
    let frameId = 0
    let disposed = false

    const paint = (bars: number[]) => {
      const width = canvas.clientWidth || 200
      const height = canvas.clientHeight || 32
      const ratio = window.devicePixelRatio || 1
      canvas.width = Math.floor(width * ratio)
      canvas.height = Math.floor(height * ratio)
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const gap = 2
      const totalBars = bars.length
      const barW = Math.max(2, (width - gap * (totalBars - 1)) / totalBars)

      // Draw bars
      bars.forEach((value, index) => {
        const barH = Math.max(3, value * height * 0.88)
        const x = index * (barW + gap)
        const y = (height - barH) / 2

        ctx.globalAlpha = 0.35 + value * 0.65
        // Orange athletic palette: center bars brighter, edge bars more muted.
        const distFromCenter = Math.abs(index - totalBars / 2) / (totalBars / 2)
        ctx.fillStyle =
          distFromCenter < 0.3
            ? "#ff6a00"
            : distFromCenter < 0.6
              ? "#e95b00"
              : "#873b12"

        ctx.beginPath()
        ctx.roundRect(x, y, barW, barH, 2)
        ctx.fill()
      })
      ctx.globalAlpha = 1

      // Edge fading via destination-out compositing.
      const fadeWidth = 20
      if (width > fadeWidth * 2 && active) {
        if (
          !gradientCacheRef.current ||
          lastWidthRef.current !== width
        ) {
          const grad = ctx.createLinearGradient(0, 0, width, 0)
          const fp = Math.min(0.25, fadeWidth / width)
          grad.addColorStop(0, "rgba(255,255,255,1)")
          grad.addColorStop(fp, "rgba(255,255,255,0)")
          grad.addColorStop(1 - fp, "rgba(255,255,255,0)")
          grad.addColorStop(1, "rgba(255,255,255,1)")
          gradientCacheRef.current = grad
          lastWidthRef.current = width
        }

        ctx.globalCompositeOperation = "destination-out"
        ctx.fillStyle = gradientCacheRef.current
        ctx.fillRect(0, 0, width, height)
        ctx.globalCompositeOperation = "source-over"
        ctx.globalAlpha = 1
      }
    }

    const draw = () => {
      if (disposed) return
      if (analyser && active && !reducedMotion) {
        analyser.getByteFrequencyData(frequency)
        paint(barsFromFrequencyData(frequency, barCount, sensitivity))
        frameId = window.requestAnimationFrame(draw)
        return
      }
      paint(Array.from({ length: barCount }, () => (active ? 0.18 : 0.06)))
    }

    draw()
    return () => {
      disposed = true
      if (frameId) window.cancelAnimationFrame(frameId)
    }
  }, [active, analyser, barCount, sensitivity])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`h-9 min-w-0 flex-1 rounded-sm ${className}`.trim()}
    />
  )
}
