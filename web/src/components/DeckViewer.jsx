import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useData } from '../lib/data';

const size = b => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
const TYPE_TAG = { PowerPoint: 'PPTX', PDF: 'PDF', Excel: 'XLSX', CSV: 'CSV' };

export default function DeckViewer({ code, teamName }) {
  const { data } = useData('downloads');
  const entry = data?.[code];
  const slides = entry?.slides ?? [];
  const [i, setI] = useState(0);
  const [dir, setDir] = useState(1);
  const stageRef = useRef(null);
  const thumbsRef = useRef(null);

  useEffect(() => setI(0), [code]);
  const go = useCallback(step => {
    if (!slides.length) return;
    setDir(step);
    setI(v => (v + step + slides.length) % slides.length);
  }, [slides.length]);

  // keyboard navigation while the viewer is in view / focused
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const onKey = e => {
      if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
    };
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  }, [go]);

  useEffect(() => {
    const t = thumbsRef.current?.children?.[i];
    t?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [i]);

  const fullscreen = () => {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };

  if (!entry) return <div className="muted">Deck files are being prepared. Run python -m src.publish_downloads.</div>;

  return (
    <div className="deck">
      {slides.length > 0 && (
        <div className="deck-viewer glass">
          <div className="deck-stage" ref={stageRef} tabIndex={0} aria-roledescription="carousel"
            aria-label={`${teamName} strategy deck, slide ${i + 1} of ${slides.length}`}>
            <AnimatePresence initial={false} custom={dir} mode="popLayout">
              <motion.img key={slides[i]} src={slides[i]} alt={`Slide ${i + 1} of ${slides.length}`}
                className="deck-slide" custom={dir}
                initial={{ opacity: 0, x: dir * 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: dir * -40 }}
                transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }} draggable={false} />
            </AnimatePresence>
            <button className="deck-nav prev" onClick={() => go(-1)} aria-label="Previous slide"><span /></button>
            <button className="deck-nav next" onClick={() => go(1)} aria-label="Next slide"><span /></button>
          </div>
          <div className="deck-bar">
            <span className="deck-count">Slide {i + 1} / {slides.length}</span>
            <button className="btn btn-ghost small" onClick={fullscreen}>Full screen</button>
          </div>
          <div className="deck-thumbs" ref={thumbsRef}>
            {slides.map((s, k) => (
              <button key={s} className={`deck-thumb ${k === i ? 'is-on' : ''}`} onClick={() => { setDir(k > i ? 1 : -1); setI(k); }}
                aria-label={`Go to slide ${k + 1}`}>
                <img src={s} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="dl-grid">
        {entry.files.map((f, k) => (
          <motion.a key={f.file} href={f.file} download className="dl-card glass"
            initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
            transition={{ delay: k * 0.05, duration: 0.5 }}>
            <span className={`dl-tag dl-${TYPE_TAG[f.type] || 'FILE'}`}>{TYPE_TAG[f.type] || f.type}</span>
            <span className="dl-label">{f.label}</span>
            <span className="dl-meta">{f.type} · {size(f.bytes)}</span>
            <span className="dl-action">Download</span>
          </motion.a>
        ))}
      </div>
    </div>
  );
}
