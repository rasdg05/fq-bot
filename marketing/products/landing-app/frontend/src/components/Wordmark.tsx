import { motion } from 'framer-motion'

/** FQ wordmark with the vertical accent bar. */
export default function Wordmark() {
  return (
    <div className="mb-[30px] inline-flex items-center gap-3">
      <motion.div
        className="h-[42px] w-[5px] rounded-[3px] bg-accent"
        initial={{ scaleY: 0, opacity: 0 }}
        animate={{ scaleY: 1, opacity: 1 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        style={{ originY: 1 }}
      />
      <div className="text-[30px] font-extrabold tracking-[-1px]">FQ</div>
    </div>
  )
}
