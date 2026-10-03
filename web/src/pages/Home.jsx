import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useScroll, useTransform } from 'framer-motion';
import { Reveal, Section, Stat, useTeamTheme } from '../components/ui';
import { TeamGrid } from './Teams';
import IndiaMap3D from '../components/IndiaMap3D';
import { useData } from '../lib/data';

export default function Home() {
  useTeamTheme('IPL');
  const { data: teams } = useData('teams');
  const { data: meta } = useData('meta');
  const hero = useRef(null);
  const { scrollYProgress } = useScroll({ target: hero, offset: ['start start', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 160]);
  const fade = useTransform(scrollYProgress, [0, 0.8], [1, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [1, 0.92]);

  const insights = meta?.market?.insights ?? [];
  const win = meta?.win_model;

  return (
    <>
      <section className="hero" ref={hero}>
        <motion.div className="hero-inner" style={{ y, opacity: fade, scale }}>
          <motion.div className="eyebrow" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
            IPL 2027 mini-auction · IPL 2028 mega-auction
          </motion.div>
          <motion.h1 className="display" initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}>
            Auction<br /><span className="grad-text">War Room.</span>
          </motion.h1>
          <motion.p className="lede hero-lede" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.9 }}>
            Who to buy, who to keep, what to pay — for all ten franchises. Built on 295,732 deliveries and
            five seasons of auction prices.
          </motion.p>
          <motion.div className="hero-ctas" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
            <Link to="/teams" className="btn btn-primary">Pick a franchise</Link>
            <Link to="/player" className="btn btn-ghost">Find a player's best team</Link>
          </motion.div>
        </motion.div>
        <div className="scroll-hint"><span /></div>
      </section>

      <div className="container">
        <Section eyebrow="The answer first" title="Three things every franchise should know.">
          <div className="stat-row">
            <Reveal delay={0}><Stat label="Revenue that is fixed central income" value={76} format={v => `${v.toFixed(0)}%`}
              sub="Winning the title vs missing the playoffs moves revenue only ~6%." /></Reveal>
            <Reveal delay={0.1}><Stat label="Price premium for an international cap" value={157} format={v => `+${v.toFixed(0)}%`}
              sub="vs +24% for each extra run/match of actual output." /></Reveal>
            <Reveal delay={0.2}><Stat label="Planned strength that shows up next season"
              value={win ? win['realisation: realised = c + rho * planned_strength'].rho * 100 : null}
              format={v => `${v.toFixed(0)}%`} sub="Bid to a ceiling and always hold a backup." /></Reveal>
          </div>
        </Section>

        <Section eyebrow="Where the market gets it wrong" title="Buy output. Don't pay for the name.">
          <div className="insight-list">
            {insights.map((s, i) => (
              <Reveal key={i} delay={i * 0.08}><div className="insight glass"><span className="insight-n">0{i + 1}</span>{s}</div></Reveal>
            ))}
          </div>
          <Reveal><Link to="/market" className="link-arrow">Explore every auction sale since 2022 →</Link></Reveal>
        </Section>

        <Section eyebrow="Ten franchises, one country" title="Every home ground plays differently.">
          <Reveal><IndiaMap3D teams={teams} /></Reveal>
        </Section>

        <Section eyebrow="Ten war rooms" title="Every squad has a different gap.">
          <TeamGrid teams={teams} />
        </Section>

        <Section eyebrow="For players" title="Which dressing room needs you most?">
          <Reveal>
            <Link to="/player" className="cta-panel glass">
              <div>
                <h3>Player Finder</h3>
                <p>Pick any player and see which franchise he would lift the most — the gap he fills, whether he
                  starts, and how much he moves their playoff chances.</p>
              </div>
              <span className="btn btn-primary">Find the fit →</span>
            </Link>
          </Reveal>
        </Section>
      </div>
    </>
  );
}
