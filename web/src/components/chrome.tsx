import { motion } from 'framer-motion'
import { NavLink } from 'react-router-dom'

export function Nav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50">
      <div className="glass-strong mx-auto mt-4 flex max-w-6xl items-center justify-between rounded-2xl px-5 py-3">
        <NavLink to="/" className="flex items-center gap-2.5">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
            <circle cx="16" cy="16" r="14" fill="none" stroke="#29e6d2" strokeWidth="2" />
            <path d="M8 20 L16 8 L24 20 Z" fill="#29e6d2" />
            <circle cx="16" cy="22" r="2.4" fill="#ff7a59" />
          </svg>
          <span className="font-[family-name:var(--font-display)] text-lg font-bold tracking-tight">
            Voyance
          </span>
          <span className="tag ml-1 hidden sm:inline">open source</span>
        </NavLink>
        <nav className="flex items-center gap-1 text-sm text-mist">
          {[
            ['/', 'Home'],
            ['/dashboard', 'Dashboard'],
            ['/research', 'Research'],
            ['/docs', 'Docs'],
          ].map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `rounded-lg px-3 py-1.5 transition-colors hover:text-foam ${isActive ? 'bg-bio/10 text-bio' : ''}`
              }
            >
              {label}
            </NavLink>
          ))}
          <a
            href="https://github.com/devansh-voyance/voyance"
            target="_blank"
            rel="noreferrer"
            className="ml-2 rounded-lg border border-bio/30 px-3 py-1.5 text-bio transition hover:bg-bio/10"
          >
            GitHub
          </a>
        </nav>
      </div>
    </header>
  )
}

export function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode
  delay?: number
  className?: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 26 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.7, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

export function Footer() {
  return (
    <footer className="mt-24 border-t border-mist/10 py-10 text-sm text-mist">
      <div className="mx-auto grid max-w-6xl gap-6 px-6 md:grid-cols-4">
        <div>
          <div className="font-[family-name:var(--font-display)] font-bold text-foam">Voyance</div>
          <p className="mt-2 leading-relaxed">
            Open-source maritime voyage intelligence. Built on NOAA MarineCadastre AIS (CC0),
            Open-Meteo ERA5 reanalysis (CC BY 4.0), and UN/LOCODE.
          </p>
        </div>
        <div>
          <div className="tag">Product</div>
          <ul className="mt-2 space-y-1">
            <li><NavLink to="/dashboard" className="hover:text-bio">Live dashboards</NavLink></li>
            <li><NavLink to="/docs" className="hover:text-bio">API & quickstart</NavLink></li>
            <li><NavLink to="/research" className="hover:text-bio">Research</NavLink></li>
          </ul>
        </div>
        <div>
          <div className="tag">Data provenance</div>
          <ul className="mt-2 space-y-1">
            <li><a className="hover:text-bio" href="https://hub.marinecadastre.gov" target="_blank" rel="noreferrer">MarineCadastre AIS (CC0)</a></li>
            <li><a className="hover:text-bio" href="https://open-meteo.com" target="_blank" rel="noreferrer">Open-Meteo ERA5 (CC BY 4.0)</a></li>
            <li><a className="hover:text-bio" href="https://unece.org/trade/cefact/UNLOCODE-Download" target="_blank" rel="noreferrer">UN/LOCODE</a></li>
          </ul>
        </div>
        <div>
          <div className="tag">License</div>
          <p className="mt-2">Apache-2.0. Not a certified navigation aid; research and decision-support use.</p>
        </div>
      </div>
      <div className="mx-auto mt-8 max-w-6xl px-6 text-xs text-mist/60">
        © 2026 Voyance contributors · marine AI can be wrong: always verify against official sources
      </div>
    </footer>
  )
}
