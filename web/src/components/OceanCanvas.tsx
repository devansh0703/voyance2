import { useEffect, useRef } from 'react'

/** Animated ocean-wave canvas for the hero — signature visual anchor. */
export default function OceanCanvas() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let w = (canvas.width = canvas.offsetWidth * devicePixelRatio)
    let h = (canvas.height = canvas.offsetHeight * devicePixelRatio)
    const onResize = () => {
      w = canvas.width = canvas.offsetWidth * devicePixelRatio
      h = canvas.height = canvas.offsetHeight * devicePixelRatio
    }
    window.addEventListener('resize', onResize)

    let raf = 0
    let t = 0
    const layers = [
      { amp: 26, len: 0.0038, speed: 0.5, y: 0.62, hue: 'rgba(41,230,210,0.10)' },
      { amp: 20, len: 0.0052, speed: 0.9, y: 0.70, hue: 'rgba(20,120,160,0.14)' },
      { amp: 16, len: 0.0075, speed: 1.3, y: 0.78, hue: 'rgba(10,60,90,0.30)' },
      { amp: 12, len: 0.0105, speed: 1.8, y: 0.86, hue: 'rgba(6,30,50,0.55)' },
    ]

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      layers.forEach((L, li) => {
        ctx.beginPath()
        ctx.moveTo(0, h)
        for (let x = 0; x <= w; x += 8) {
          const y =
            h * L.y +
            Math.sin(x * L.len + t * L.speed + li * 2.1) * L.amp * devicePixelRatio +
            Math.sin(x * L.len * 2.7 + t * L.speed * 1.7) * L.amp * 0.4 * devicePixelRatio
          ctx.lineTo(x, y)
        }
        ctx.lineTo(w, h)
        ctx.closePath()
        ctx.fillStyle = L.hue
        ctx.fill()
      })
      t += reduce ? 0 : 0.016
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  return <canvas ref={ref} className="absolute inset-0 h-full w-full" aria-hidden="true" />
}
