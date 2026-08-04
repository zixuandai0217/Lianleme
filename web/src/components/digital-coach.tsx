/* Render the shared coach as aligned 2D image layers with restrained CSS motion. */
import { useCallback, useEffect, useState } from "react"
import type { CoachViseme } from "@/components/coach-lip-sync"

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"
const BLINK_MIN_MS = 3_200
const BLINK_MAX_MS = 5_800
const BLINK_CLOSED_MS = 92

export type DigitalCoachState = "idle" | "listening" | "thinking" | "speaking" | "error"

export interface DigitalCoachProps {
  state: DigitalCoachState
  variant: "stage" | "portrait"
  viseme?: CoachViseme
  ariaLabel: string
  className?: string
}

type AssetStatus = "loading" | "ready" | "fallback" | "error"
type BlinkState = "open" | "closed"
type BodySource = "primary" | "fallback"

const PRIMARY_BODY_ASSET = "/coach/v2/coach-base.webp"
const FALLBACK_BODY_ASSET = "/coach/rock-coach.webp"
const FACE_ASSETS = {
  mouths: {
    A: "/coach/v2/face/mouth-A.webp",
    B: "/coach/v2/face/mouth-B.webp",
    C: "/coach/v2/face/mouth-C.webp",
    D: "/coach/v2/face/mouth-D.webp",
    E: "/coach/v2/face/mouth-E.webp",
    F: "/coach/v2/face/mouth-F.webp",
    G: "/coach/v2/face/mouth-G.webp",
    H: "/coach/v2/face/mouth-H.webp",
    X: "/coach/v2/face/mouth-X.webp",
  } satisfies Record<CoachViseme, string>,
  eyesBlink: "/coach/v2/face/eyes-blink.webp",
  browThinking: "/coach/v2/face/brow-thinking.webp",
} as const

const FACE_ASSET_URLS = [
  ...Object.values(FACE_ASSETS.mouths),
  FACE_ASSETS.eyesBlink,
  FACE_ASSETS.browThinking,
]

// Track the operating-system motion preference without changing audio playback.
function useReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia?.(REDUCED_MOTION_QUERY).matches ?? false,
  )

  useEffect(() => {
    const media = window.matchMedia?.(REDUCED_MOTION_QUERY)
    if (!media) return
    const updatePreference = () => setReducedMotion(media.matches)
    updatePreference()
    media.addEventListener("change", updatePreference)
    return () => media.removeEventListener("change", updatePreference)
  }, [])

  return reducedMotion
}

// Present one aligned character in a full stage or cropped dashboard portrait.
export function DigitalCoach({
  state,
  variant,
  viseme = "X",
  ariaLabel,
  className = "",
}: DigitalCoachProps) {
  const reducedMotion = useReducedMotion()
  const [assetStatus, setAssetStatus] = useState<AssetStatus>("loading")
  const [bodySource, setBodySource] = useState<BodySource>("primary")
  const [blinkState, setBlinkState] = useState<BlinkState>("open")
  const [failedFaceAssets, setFailedFaceAssets] = useState<Set<string>>(() => new Set())

  const markFaceAssetFailed = useCallback((url: string) => {
    setFailedFaceAssets((current) => {
      if (current.has(url)) return current
      const next = new Set(current)
      next.add(url)
      return next
    })
  }, [])

  useEffect(() => {
    let active = true
    const urls = variant === "stage" ? FACE_ASSET_URLS : [FACE_ASSETS.mouths.X]
    const images = urls.map((url) => {
      const image = new Image()
      image.decoding = "async"
      image.onerror = () => {
        if (active) markFaceAssetFailed(url)
      }
      image.src = url
      return image
    })

    return () => {
      active = false
      images.forEach((image) => {
        image.onerror = null
      })
    }
  }, [markFaceAssetFailed, variant])

  useEffect(() => {
    if (variant !== "stage" || reducedMotion) return

    let disposed = false
    let nextBlinkTimer = 0
    let reopenTimer = 0

    const scheduleBlink = () => {
      const delay = BLINK_MIN_MS + Math.random() * (BLINK_MAX_MS - BLINK_MIN_MS)
      nextBlinkTimer = window.setTimeout(() => {
        if (disposed) return
        setBlinkState("closed")
        reopenTimer = window.setTimeout(() => {
          if (disposed) return
          setBlinkState("open")
          scheduleBlink()
        }, BLINK_CLOSED_MS)
      }, delay)
    }

    scheduleBlink()
    return () => {
      disposed = true
      window.clearTimeout(nextBlinkTimer)
      window.clearTimeout(reopenTimer)
      setBlinkState("open")
    }
  }, [reducedMotion, variant])

  const displayViseme = variant === "stage"
    && state === "speaking"
    && !reducedMotion
    ? viseme
    : "X"
  const mouthAsset = FACE_ASSETS.mouths[displayViseme]
  const displayBlink = variant === "stage" && !reducedMotion ? blinkState : "open"
  const animationProfile = variant === "stage" && state === "speaking" ? "speech" : "breath"
  const bodyAsset = bodySource === "primary" ? PRIMARY_BODY_ASSET : FALLBACK_BODY_ASSET
  const bodyVisible = assetStatus === "ready" || assetStatus === "fallback"
  const bodyClassName = variant === "portrait"
    ? "bottom-[-63%] h-[180%]"
    : "bottom-[-4%] h-[96%]"

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      data-coach-renderer="layered-2d"
      data-coach-state={state}
      data-coach-variant={variant}
      data-asset-status={assetStatus}
      data-viseme={displayViseme}
      data-blink={displayBlink}
      data-motion={reducedMotion ? "reduced" : "full"}
      data-animation-profile={animationProfile}
      className={`relative isolate w-full overflow-hidden ${variant === "portrait" ? "aspect-square bg-transparent" : "min-h-80 bg-[#111511]"} ${className}`.trim()}
    >
      {variant === "stage" && (
        <div aria-hidden="true" className="absolute inset-0 overflow-hidden">
          <span className="absolute inset-y-0 left-0 w-3 bg-[#ff6a00]" />
          <span className="absolute top-[18%] right-0 h-px w-[34%] bg-[#f4f0e8]/28" />
          <span className="absolute right-0 bottom-[12%] h-3 w-[38%] bg-[#ff6a00]" />
          <span className="absolute bottom-[12%] left-0 h-px w-full bg-[#f4f0e8]/16" />
        </div>
      )}

      <div aria-hidden="true" className="coach-sprite-motion absolute inset-0 z-[1] origin-bottom motion-reduce:animate-none">
        <div className={`absolute left-1/2 aspect-square max-h-none -translate-x-1/2 ${bodyClassName}`}>
          <img
            src={bodyAsset}
            alt=""
            draggable={false}
            data-coach-layer="body"
            onLoad={() => setAssetStatus(bodySource === "primary" ? "ready" : "fallback")}
            onError={() => {
              if (bodySource === "primary") {
                setBodySource("fallback")
                setAssetStatus("loading")
                return
              }
              setAssetStatus("error")
            }}
            className={`absolute inset-0 size-full object-contain drop-shadow-[0_24px_24px_rgba(0,0,0,0.32)] transition-opacity duration-200 ${bodyVisible ? "opacity-100" : "opacity-0"}`}
          />

          {bodySource === "primary" && (
            <div
              data-face-rig="layered"
              className={`pointer-events-none absolute inset-0 size-full transition-opacity duration-200 ${assetStatus === "ready" ? "opacity-100" : "opacity-0"}`}
            >
              {!failedFaceAssets.has(mouthAsset) && (
                <img
                  src={mouthAsset}
                  alt=""
                  draggable={false}
                  data-coach-layer="mouth"
                  onError={() => markFaceAssetFailed(mouthAsset)}
                  className="absolute inset-0 size-full object-contain"
                />
              )}
              {variant === "stage" && !failedFaceAssets.has(FACE_ASSETS.eyesBlink) && (
                <img
                  src={FACE_ASSETS.eyesBlink}
                  alt=""
                  draggable={false}
                  data-coach-layer="eyes-closed"
                  onError={() => markFaceAssetFailed(FACE_ASSETS.eyesBlink)}
                  className="coach-eye-blink-layer absolute inset-0 size-full object-contain opacity-0"
                />
              )}
              {variant === "stage" && state === "thinking" && !reducedMotion && !failedFaceAssets.has(FACE_ASSETS.browThinking) && (
                <img
                  src={FACE_ASSETS.browThinking}
                  alt=""
                  draggable={false}
                  data-coach-layer="brow-thinking"
                  onError={() => markFaceAssetFailed(FACE_ASSETS.browThinking)}
                  className="absolute inset-0 size-full object-contain"
                />
              )}
            </div>
          )}
        </div>
      </div>

      {assetStatus === "loading" && (
        <span
          aria-hidden="true"
          className="absolute top-1/2 left-1/2 z-[2] size-7 -translate-1/2 animate-pulse rounded-full border-2 border-[#ff6a00] border-r-white/20 motion-reduce:animate-none"
        />
      )}

      {assetStatus === "error" && (
        <div aria-hidden="true" className="absolute inset-0 z-[2] grid place-items-center">
          <span className="grid size-16 place-items-center rounded-full border-2 border-[#ff6a00] bg-[#151a16] font-heading text-2xl font-bold text-[#ff6a00]">C</span>
        </div>
      )}
    </div>
  )
}
