import { useState, type FormEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fadeUp, inViewProps } from '../lib/motion'
import { LINKS } from '../lib/constants'

type Status = 'idle' | 'loading' | 'success' | 'error'

const BULLETS = [
  <>
    <b className="font-semibold text-ink">Regla 1–5</b> del trading con sistema, explicadas con
    ejemplos reales.
  </>,
  <>
    Gestión de riesgo, R:R y <b className="font-semibold text-ink">tamaño de posición</b> (con
    números).
  </>,
  <>
    Checklist de trade + cómo <b className="font-semibold text-ink">medir y mejorar</b>.
  </>,
]

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function OfferCard() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (status === 'loading') return

    if (!EMAIL_RE.test(email)) {
      setStatus('error')
      setErrorMsg('Escribe un correo válido para poder enviarte la guía.')
      return
    }

    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!res.ok) throw new Error('bad_status')
      const data = (await res.json()) as { ok: boolean }
      if (!data.ok) throw new Error('not_ok')
      setStatus('success')
    } catch {
      setStatus('error')
      setErrorMsg('Algo falló al enviar. Inténtalo de nuevo o escríbeme por Telegram.')
    }
  }

  return (
    <motion.div
      id="guia"
      variants={fadeUp}
      {...inViewProps}
      className="mx-auto my-[26px] rounded-[20px] border border-hairline bg-panel px-[26px] py-[30px]"
    >
      <h2 className="text-[24px] tracking-[-.4px]">Descarga la guía gratis</h2>

      <ul className="my-4 mb-[22px] list-none space-y-2.5">
        {BULLETS.map((b, i) => (
          <li key={i} className="flex items-start gap-2.5 text-[15px] text-muted">
            <span className="font-mono text-accent">›</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>

      <AnimatePresence mode="wait">
        {status === 'success' ? (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="rounded-xl border border-accent2 bg-[#0c1a16] px-5 py-6 text-center"
          >
            <div className="text-[22px]">Revisa tu correo 📩</div>
            <p className="mt-2 text-[15px] text-muted">
              Te mandé la guía. Si no la ves, mira en spam o promociones.
            </p>
            <a
              href={LINKS.telegramDM}
              className="mt-4 inline-flex items-center justify-center rounded-xl bg-[#229ED9] px-[22px] py-[13px] text-[15px] font-extrabold text-white"
            >
              Entra a la comunidad en Telegram ›
            </a>
          </motion.div>
        ) : (
          <motion.div key="form" exit={{ opacity: 0 }}>
            <form onSubmit={handleSubmit} className="flex flex-wrap gap-2.5" noValidate>
              <input
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Tu mejor correo"
                aria-label="Correo electrónico"
                required
                className="min-w-[200px] flex-1 rounded-xl border border-hairline bg-[#0c0f14] px-4 py-[15px] text-base text-ink outline-none transition focus:border-accent placeholder:text-faint"
              />
              <motion.button
                type="submit"
                disabled={status === 'loading'}
                whileHover={{ scale: status === 'loading' ? 1 : 1.03 }}
                whileTap={{ scale: 0.97 }}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-[22px] py-[15px] text-base font-extrabold text-[#06140f] disabled:opacity-70"
              >
                {status === 'loading' ? 'Enviando…' : 'Quiero la guía ›'}
              </motion.button>
            </form>

            {status === 'error' && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="mt-2.5 text-xs text-[#f08a8a]"
              >
                {errorMsg}
              </motion.div>
            )}

            <div className="mt-2.5 text-xs text-faint">
              Cero spam. Te llega al correo y entras a la comunidad.
            </div>

            <div className="my-4 mb-1 text-center text-[13px] tracking-[1px] text-faint">
              — o entra directo —
            </div>
            <motion.a
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              href={LINKS.telegramDM}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-[#229ED9] px-[22px] py-[15px] text-base font-extrabold text-white"
            >
              Escríbeme «FQ» en Telegram
            </motion.a>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
