import { motion } from 'framer-motion'
import Wordmark from './Wordmark'
import VideoSlot from './VideoSlot'
import { fadeUp, stagger } from '../lib/motion'

export default function Hero() {
  return (
    <header className="relative overflow-hidden pb-[30px] pt-[54px] text-center">
      {/* Campo de partículas doradas (fondo de marca, generado con Higgsfield). */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-20 bg-cover bg-center opacity-[.55]"
        style={{ backgroundImage: "url('/fq-bg.webp')" }}
      />
      {/* Glow dorado + degradado para legibilidad del texto sobre el fondo. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 animate-glowPulse"
        style={{
          background:
            'radial-gradient(120% 70% at 50% -10%, rgba(212,175,55,.18), transparent 55%), linear-gradient(180deg, rgba(5,7,5,.30) 0%, rgba(5,7,5,.70) 80%, #050705 100%)',
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
            Deja de dibujar rayitas.
            <br />
            Aprende a leer <span className="text-accent">la liquidez</span>.
          </motion.h1>

          <motion.p variants={fadeUp} className="mx-auto max-w-[560px] text-[18px] text-muted">
            Te regalo <b className="font-semibold text-ink">La Receta de la Liquidez</b>: las 3
            cosas que de verdad mueven el precio, en una hoja. Sin humo. Sin promesas.
          </motion.p>

          <motion.div variants={fadeUp}>
            <VideoSlot />
          </motion.div>
        </motion.div>
      </div>
    </header>
  )
}
