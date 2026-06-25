import { motion } from 'framer-motion'
import { fadeUp, stagger, inViewProps } from '../lib/motion'

type Item = { n: string; t: string; d: string; accent?: boolean }

const ITEMS: Item[] = [
  { n: '01', t: 'Define tu invalidación', d: 'Dónde te equivocas, antes de entrar. El stop no es opcional.' },
  { n: '02', t: 'Arriesga siempre lo mismo', d: 'El tamaño de posición que te mantiene en el juego.' },
  { n: '03', t: 'Plan: entrada, stop, target', d: 'R:R que te hace rentable sin adivinar.' },
  { n: '04', t: 'Reglas, no emociones', d: 'Proceso por encima del resultado. Cero ego.' },
  { n: '05', t: 'Mide y mejora', d: 'Bitácora + backtesting. Datos, no fe.' },
  { n: '+', t: 'El bot FQ', d: 'Señal lista: entrada, stop y target, multi-símbolo.', accent: true },
]

export default function ValueGrid() {
  return (
    <section className="pb-1.5 pt-[18px]">
      <motion.h3
        variants={fadeUp}
        {...inViewProps}
        className="mb-[18px] text-center text-[13px] uppercase tracking-[2px] text-faint"
      >
        Lo que vas a aprender
      </motion.h3>

      <motion.div
        variants={stagger}
        {...inViewProps}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        {ITEMS.map((item) => (
          <motion.div
            key={item.n}
            variants={fadeUp}
            whileHover={{ y: -3 }}
            className={`rounded-[14px] border bg-panel p-4 ${
              item.accent ? 'border-accent2' : 'border-hairline'
            }`}
          >
            <div className="font-mono text-[13px] text-accent">{item.n}</div>
            <div className="mb-1 mt-1.5 font-bold">{item.t}</div>
            <div className="text-[13.5px] text-muted">{item.d}</div>
          </motion.div>
        ))}
      </motion.div>
    </section>
  )
}
