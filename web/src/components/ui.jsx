import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { animate, motion, useInView, useReducedMotion } from 'framer-motion';
import ColorBends from './ColorBends';
import { theme } from '../lib/themes';

// ---------------------------------------------------------------- theme
export const ThemeCtx = createContext({ code: 'IPL', setCode: () => {} });
export const useTeamTheme = code => {
  const { setCode } = useContext(ThemeCtx);
  useEffect(() => { setCode(code || 'IPL'); }, [code, setCode]);
};

export function Background({ code }) {
  const t = theme(code);
  const reduce = useReducedMotion();
  return (
    <div className="bg" aria-hidden="true" style={{ background: t.base }}>
      {reduce ? (
        <div className="bg-static" style={{
          background: `radial-gradient(60% 50% at 20% 20%, ${t.bends[0]}55, transparent 70%),
                       radial-gradient(50% 50% at 80% 70%, ${t.bends[1]}55, transparent 70%)` }} />
      ) : (
        <ColorBends colors={t.bends} rotation={35} speed={0.18} scale={1.15} frequency={1}
          warpStrength={1} mouseInfluence={0.8} noise={0.08} parallax={0.5} iterations={1}
          intensity={1.0} bandWidth={6} transparent />
      )}
      <div className="bg-veil" />
    </div>
  );
}

// ---------------------------------------------------------------- logos
// Uses /logos/<CODE>.png when you add one; otherwise an original crest.
export function TeamLogo({ code, size = 64, className = '' }) {
  const [failed, setFailed] = useState(false);
  if (!failed) {
    return (
      <img src={`/logos/${code}.png`} alt={`${theme(code).name} logo`} width={size} height={size}
        className={`logo-img ${className}`} onError={() => setFailed(true)} />
    );
  }
  return <Crest code={code} size={size} className={className} />;
}

export function Crest({ code, size = 64, className = '' }) {
  const t = theme(code);
  const id = `g-${code}`;
  const label = t.monogram || code;
  return (
    <svg className={`crest ${className}`} width={size} height={size} viewBox="0 0 100 110" role="img"
      aria-label={`${t.name} crest`}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={t.bends[0]} />
          <stop offset="100%" stopColor={t.bends[1]} />
        </linearGradient>
      </defs>
      <path d="M50 4 L92 18 V54 C92 80 72 98 50 106 C28 98 8 80 8 54 V18 Z" fill={`url(#${id})`}
        stroke={t.accent2} strokeWidth="3" />
      {/* crossed bat + ball */}
      <g opacity="0.28" fill="#fff">
        <rect x="46" y="20" width="8" height="58" rx="3" transform="rotate(-35 50 50)" />
        <rect x="46" y="20" width="8" height="58" rx="3" transform="rotate(35 50 50)" />
      </g>
      <circle cx="74" cy="30" r="7" fill={t.accent2} stroke="#fff" strokeWidth="1.5" />
      <path d="M69 27 Q74 30 69 33 M79 27 Q74 30 79 33" stroke="#fff" strokeWidth="1" fill="none" />
      <text x="50" y="68" textAnchor="middle" fontFamily="Inter, sans-serif" fontWeight="900"
        fontSize={label.length > 2 ? 22 : 28} fill="#fff" letterSpacing="1">{label}</text>
      {/* stumps */}
      <g fill="#fff" opacity="0.85">
        <rect x="41" y="78" width="3" height="14" rx="1" />
        <rect x="48.5" y="78" width="3" height="14" rx="1" />
        <rect x="56" y="78" width="3" height="14" rx="1" />
        <rect x="40" y="76" width="20" height="2" rx="1" />
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------- motion
export function Reveal({ children, delay = 0, y = 32, className = '', as = 'div' }) {
  const M = motion[as];
  return (
    <M className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}>
      {children}
    </M>
  );
}

export function Counter({ value, format = v => v.toFixed(0), className = '' }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!inView || value == null) return;
    const c = animate(0, value, { duration: 1.4, ease: [0.16, 1, 0.3, 1], onUpdate: setShown });
    return () => c.stop();
  }, [inView, value]);
  return <span ref={ref} className={className}>{value == null ? '—' : format(shown)}</span>;
}

export function Stat({ label, value, format, sub }) {
  return (
    <div className="stat glass">
      <div className="stat-label">{label}</div>
      <div className="stat-value"><Counter value={value} format={format} /></div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Section({ eyebrow, title, children, id }) {
  return (
    <section className="section" id={id}>
      <Reveal>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2 className="section-title">{title}</h2>
      </Reveal>
      {children}
    </section>
  );
}

const STATUS_TXT = { Green: 'Starter quality', Amber: 'Needs an upgrade', Red: 'Gap to fill' };
export function CoverageGrid({ rows, onPick, active }) {
  return (
    <div className="cov-grid">
      {rows.map((r, i) => (
        <motion.button key={r.role} type="button"
          className={`cov-tile cov-${r.status} ${active === r.role ? 'is-active' : ''}`}
          onClick={() => onPick && onPick(r.role)}
          initial={{ opacity: 0, scale: 0.92 }} whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }} transition={{ delay: i * 0.04, duration: 0.5 }}
          title={r.explanation}>
          <span className="cov-status"><span className="cov-dot" />{r.status}</span>
          <span className="cov-role">{r.role}</span>
          <span className="cov-sub">{STATUS_TXT[r.status]}</span>
          <span className="cov-best">{r.best_player || 'No cover'}</span>
        </motion.button>
      ))}
    </div>
  );
}

export function Pill({ children, tone = '' }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}
