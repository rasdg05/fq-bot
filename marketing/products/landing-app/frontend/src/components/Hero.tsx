import { motion } from 'framer-motion'
import Wordmark from './Wordmark'
import VideoSlot from './VideoSlot'
import { fadeUp, stagger } from '../lib/motion'

export default function Hero() {
  return (
    <header className="relative overflow-hidden pb-[30px] pt-[54px] text-center">
      {/* Soft accent radial glow at the top, gently pulsing. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 animate-glowPulse"
        style={{
          background:
            'radial-gradient(120% 70% at 50% -10%, rgba(212,175,55,.22), transparent 60%)',
        }}
      />

      <div className="wrap">
        <motion.div variants={stagger} initial="hidden" animate="show">
          <motion.div variants={fadeUp}>
            <Wordmark />
          </motion.div>

          <motion.div
            variants={fadeUp}
            className="font-mono text-xs uppercase tracking-[3px] text-accent"
          >
            Fibonacci Cuántico
          </motion.div>

          <motion.h1
            variants={fadeUp}
            className="mx-auto mb-3 mt-3.5 text-[31px] font-bold leading-[1.06] tracking-[-1px] sm:text-[40px]"
          >
            Deja de operar <span className="text-accent">a corazonada</span>.
            <br />
            Empieza con sistema.
          </motion.h1>

          <motion.p variants={fadeUp} className="mx-auto max-w-[560px] text-[18px] text-muted">
            Te regalo la guía con las <b className="font-semibold text-ink">5 reglas</b> que
            separan al que opera con método del que opera con el ego. Sin humo. Sin promesas.
          </motion.p>

          <motion.div variants={fadeUp}>
            <VideoSlot />
          </motion.div>
        </motion.div>
      </div>
    </header>
  )
}
