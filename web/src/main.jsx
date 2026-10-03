import { StrictMode, Suspense, lazy, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Background, ThemeCtx } from './components/ui';
import Nav from './components/Nav';
// Pages load on demand so the first visit downloads only what it shows.
const Home = lazy(() => import('./pages/Home'));
const Teams = lazy(() => import('./pages/Teams'));
const Team = lazy(() => import('./pages/Team'));
const PlayerFinder = lazy(() => import('./pages/PlayerFinder'));
const Market = lazy(() => import('./pages/Market'));
const Method = lazy(() => import('./pages/Method'));
import { theme } from './lib/themes';
import './styles.css';

function Routed() {
  const loc = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.main key={loc.pathname} className="page"
        initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        onAnimationStart={() => window.scrollTo({ top: 0 })}>
        <Suspense fallback={<div className="container loading">Loading…</div>}>
        <Routes location={loc}>
          <Route path="/" element={<Home />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/team/:code" element={<Team />} />
          <Route path="/player" element={<PlayerFinder />} />
          <Route path="/player/:id" element={<PlayerFinder />} />
          <Route path="/market" element={<Market />} />
          <Route path="/method" element={<Method />} />
          <Route path="*" element={<Home />} />
        </Routes>
        </Suspense>
      </motion.main>
    </AnimatePresence>
  );
}

function App() {
  const [code, setCode] = useState('IPL');
  const t = theme(code);
  const ctx = useMemo(() => ({ code, setCode }), [code]);
  return (
    <ThemeCtx.Provider value={ctx}>
      <div className="app" style={{ '--accent': t.accent, '--accent-2': t.accent2, '--accent-ink': t.ink, '--base': t.base }}>
        <Background code={code} />
        <BrowserRouter>
          <Nav />
          <Routed />
          <footer className="footer">
            Data: Cricsheet ball-by-ball (to 31 May 2026) · Wikipedia auction tables · public brand & rights figures.
            Hypothetical consulting analysis — not affiliated with the IPL or any franchise.
          </footer>
        </BrowserRouter>
      </div>
    </ThemeCtx.Provider>
  );
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>);
