import { motion } from 'framer-motion'
import { fadeUp, inViewProps } from '../lib/motion'

/** TJR-style honesty strip + prominent risk disclaimer. */
export default function Transparency() {
  return (
    <motion.section
      variants={fadeUp}
      {...inViewProps}
      className="my-[26px] rounded-[20px] border border-hairline bg-panel2 px-[26px] py-[26px]"
    >
      <div className="font-mono text-xs uppercase tracking-[2px] text-accent">
        Transparencia
      </div>
      <p className="mt-2.5 text-[16px] text-ink">
        Aquí no se vende humo. Se muestran trades que ganan{' '}
        <b className="font-semibold">y los que pierden</b>. Sistema por encima del ego, datos por
        encima de la fe.
      </p>
      <p className="mt-3 text-[13px] leading-relaxed text-muted">
        <b className="font-semibold text-ink">Aviso de riesgo:</b> el trading conlleva alto riesgo
        y puedes perder todo tu capital. Esto es contenido educativo, no asesoría financiera ni
        promesa de rendimiento. Rendimientos pasados no garantizan resultados futuros.
      </p>
    </motion.section>
  )
}
