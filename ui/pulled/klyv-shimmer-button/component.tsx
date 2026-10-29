/*
MIT License

Copyright (c) 2026 Klyv contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
import "./klyv-shimmer-button-utils/klyv-theme.css";
'use client'

import { useRef, type ButtonHTMLAttributes, type PointerEvent, type ReactNode } from 'react'
import { cn } from "./klyv-shimmer-button-utils/lib-cn"

export type ShimmerTone = 'accent' | 'ink' | 'glass'

const TONES: Record<ShimmerTone, { shell: string; sheen: string; glow: string }> = {
  accent: {
    shell: 'bg-accent text-accent-ink shadow-[var(--shadow-tile)] hover:bg-accent-strong',
    sheen: 'bg-white/70',
    glow: 'rgba(255,255,255,0.55)',
  },
  ink: {
    shell: 'bg-ink text-ink-inverse shadow-[var(--shadow-float)]',
    sheen: 'bg-white/35',
    glow: 'rgba(200,242,78,0.45)',
  },
  glass: {
    shell: 'border border-line-strong bg-surface text-ink shadow-[var(--shadow-tile)] hover:bg-surface-muted',
    sheen: 'bg-accent/45',
    glow: 'rgba(200,242,78,0.5)',
  },
}

const SIZES = {
  sm: 'h-8 px-3.5 text-[12px]',
  md: 'h-10 px-5 text-[13px]',
  lg: 'h-12 px-6 text-[14px]',
} as const

export type ShimmerButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** The button label. */
  children: ReactNode
  tone?: ShimmerTone
  size?: keyof typeof SIZES
  /** Seconds between sweeps. */
  duration?: number
  /** Sweep only on hover and focus, rather than continuously. */
  onHover?: boolean
  /** Add a soft light that follows the pointer across the face. */
  glow?: boolean
  /** Stretch to the container width. */
  fullWidth?: boolean
}

/**
 * A call to action with a sheen sweeping across it and a light that follows
 * the pointer.
 *
 * Both effects are one extra span each, clipped by the button, so the label
 * keeps its own stacking context and stays selectable and readable throughout.
 * The pointer light is written to CSS custom properties on the element rather
 * than to React state: a pointer move fires far more often than a frame, and
 * routing it through state would re-render the whole subtree for a value only
 * the compositor reads.
 *
 * `onHover` exists because a sweep that never stops is fine on one hero button
 * and exhausting on a toolbar of six.
 */
export function ShimmerButton({
  children,
  tone = 'accent',
  size = 'md',
  duration = 3,
  onHover = false,
  glow = true,
  fullWidth = false,
  className,
  onPointerMove,
  ...props
}: ShimmerButtonProps) {
  const ref = useRef<HTMLButtonElement>(null)
  const palette = TONES[tone]

  const handlePointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    onPointerMove?.(event)
    if (!glow) return
    const node = ref.current
    if (!node) return
    const rect = node.getBoundingClientRect()
    node.style.setProperty('--glow-x', `${event.clientX - rect.left}px`)
    node.style.setProperty('--glow-y', `${event.clientY - rect.top}px`)
    node.style.setProperty('--glow-opacity', '1')
  }

  return (
    <button
      ref={ref}
      type="button"
      onPointerMove={handlePointerMove}
      onPointerLeave={() => ref.current?.style.setProperty('--glow-opacity', '0')}
      className={cn(
        'group/shimmer relative isolate inline-flex shrink-0 items-center justify-center gap-2 overflow-hidden rounded-full font-bold leading-none transition-colors',
        'disabled:pointer-events-none disabled:opacity-40',
        palette.shell,
        SIZES[size],
        fullWidth && 'w-full',
        className,
      )}
      {...props}
    >
      {glow && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -z-10 h-[150px] w-[150px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[var(--glow-opacity,0)] blur-2xl transition-opacity duration-[var(--duration-slow)]"
          style={{
            left: 'var(--glow-x, 50%)',
            top: 'var(--glow-y, 50%)',
            background: `radial-gradient(circle, ${palette.glow} 0%, transparent 70%)`,
          }}
        />
      )}
      <span
        aria-hidden="true"
        className={cn(
          'motion-safe-only pointer-events-none absolute inset-y-0 -z-10 w-1/3 blur-[6px]',
          palette.sheen,
          // Paused rather than unmounted, so the sweep starts from the left
          // edge the moment the pointer arrives instead of mid-travel.
          onHover &&
            'opacity-0 [animation-play-state:paused] group-hover/shimmer:opacity-100 group-hover/shimmer:[animation-play-state:running] group-focus-visible/shimmer:opacity-100 group-focus-visible/shimmer:[animation-play-state:running]',
        )}
        style={{ animation: `shimmer-sweep ${duration}s ease-in-out infinite` }}
      />
      <span className="relative inline-flex items-center gap-2">{children}</span>
    </button>
  )
}

export default ShimmerButton;
