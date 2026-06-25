import type { Variants } from 'framer-motion'

/**
 * Shared motion primitives. Subtle fade + slide-up, premium easing.
 * Framer Motion automatically honours prefers-reduced-motion when the global
 * MotionConfig reducedMotion="user" is set (see App.tsx).
 */

const EASE = [0.22, 1, 0.36, 1] as const

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, ease: EASE },
  },
}

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.6, ease: EASE } },
}

/** Parent container that staggers its children's entrance. */
export const stagger: Variants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.09, delayChildren: 0.05 },
  },
}

/** Standard whileInView config: animate once when ~20% enters the viewport. */
export const inViewProps = {
  initial: 'hidden' as const,
  whileInView: 'show' as const,
  viewport: { once: true, amount: 0.2 },
}
