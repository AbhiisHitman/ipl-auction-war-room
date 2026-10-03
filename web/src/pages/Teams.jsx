import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Pill, Reveal, TeamLogo, useTeamTheme } from '../components/ui';
import { useData } from '../lib/data';
import { TEAM_CODES, theme } from '../lib/themes';
import { ordinal } from '../lib/format';
import IndiaMap3D from '../components/IndiaMap3D';

export function TeamGrid({ teams }) {
  return (
    <div className="team-grid">
      {TEAM_CODES.map((c, i) => {
        const t = teams?.[c];
        const th = theme(c);
        const reds = t?.brief?.red_roles?.length ?? 0;
        return (
          <motion.div key={c} initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }} transition={{ delay: (i % 5) * 0.06, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}>
            <Link to={`/team/${c}`} className="team-card" style={{
              '--c1': th.bends[0], '--c2': th.bends[1], '--c3': th.accent2 }}>
              <div className="team-card-glow" />
              <TeamLogo code={c} size={72} />
              <div className="team-card-name">{th.name}</div>
              {t && (
                <div className="team-card-meta">
                  <span>{ordinal(t.brief.finish_2026)} in 2026</span>
                  <Pill tone={t.brief.stance === 'Win Now' ? 'pill-win' : 'pill-build'}>{t.brief.stance}</Pill>
                </div>
              )}
              {t && <div className="team-card-gaps">{reds ? `${reds} red gap${reds > 1 ? 's' : ''}: ${t.brief.red_roles.join(', ')}` : 'No red gaps'}</div>}
              <span className="team-card-cta">Open war room →</span>
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}

export default function Teams() {
  useTeamTheme('IPL');
  const { data } = useData('teams');
  return (
    <div className="container">
      <Reveal className="page-head">
        <div className="eyebrow">Ten franchises · ten different plans</div>
        <h1 className="display-sm">Choose a war room.</h1>
        <p className="lede">Every team has its own gaps, home ground and budget, so every plan is different.</p>
      </Reveal>
      <IndiaMap3D teams={data} height={560} />
      <div className="spacer" />
      <TeamGrid teams={data} />
    </div>
  );
}
