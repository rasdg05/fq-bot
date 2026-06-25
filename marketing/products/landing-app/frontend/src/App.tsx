import { MotionConfig } from 'framer-motion'
import Hero from './components/Hero'
import OfferCard from './components/OfferCard'
import ValueGrid from './components/ValueGrid'
import Transparency from './components/Transparency'
import SecondaryLinks from './components/SecondaryLinks'
import Footer from './components/Footer'

export default function App() {
  return (
    // reducedMotion="user" -> Framer Motion disables non-essential motion
    // automatically for users with prefers-reduced-motion set.
    <MotionConfig reducedMotion="user">
      <Hero />
      <main className="wrap">
        <OfferCard />
        <ValueGrid />
        <Transparency />
        <SecondaryLinks />
      </main>
      <Footer />
    </MotionConfig>
  )
}
