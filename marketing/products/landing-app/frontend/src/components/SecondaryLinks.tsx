import { motion } from 'framer-motion'
import { fadeUp, stagger, inViewProps } from '../lib/motion'
import { LINKS } from '../lib/constants'

const ITEMS = [
  { href: LINKS.instagram, label: 'Instagram', handle: LINKS.instagramHandle },
  { href: LINKS.telegramDM, label: 'Telegram', handle: LINKS.telegramHandle },
  { href: LINKS.bot, label: 'Bot', handle: LINKS.botHandle },
]

export default function SecondaryLinks() {
  return (
    <motion.div
      variants={stagger}
      {...inViewProps}
      className="my-6 flex flex-wrap justify-center gap-2.5"
    >
      {ITEMS.map((item) => (
        <motion.a
          key={item.href}
          variants={fadeUp}
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-full border border-hairline bg-panel px-4 py-2.5 text-sm text-muted"
        >
          {item.label} <b className="text-ink">{item.handle}</b>
        </motion.a>
      ))}
    </motion.div>
  )
}
