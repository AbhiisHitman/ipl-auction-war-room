import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Pill, Reveal, Stat, TeamLogo, useTeamTheme } from '../components/ui';
import { useData } from '../lib/data';
import { theme } from '../lib/themes';
import { cr, pct, roleList, signed } from '../lib/format';

function PhaseBars({ p }) {
  const vals = [['Powerplay', p.impact_Powerplay], ['Middle overs', p.impact_Middle], ['Death overs', p.impact_Death]];
  const max = Math.max(1, ...vals.map(([, v]) => Math.abs(v || 0)));
  return (
    <div className="phase-bars">
      {vals.map(([k, v]) => (
        <div key={k} className="phase-row">
          <span>{k}</span>
          <div className="phase-track">
            <motion.div className={`phase-fill ${v < 0 ? 'neg' : ''}`} initial={{ width: 0 }}
              animate={{ width: `${(Math.abs(v || 0) / max) * 50}%` }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }} />
          </div>
          <b>{signed(v)}</b>
        </div>
      ))}
    </div>
  );
}

function FitRow({ f, i, best }) {
  const max = best?.fit_gain || 1;
  const th = theme(f.team);
  return (
    <motion.div className={`fit-row ${i === 0 ? 'is-best' : ''}`} style={{ '--team': th.accent }}
      initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05, duration: 0.5 }}>
      <span className="fit-rank">{i + 1}</span>
      <Link to={`/team/${f.team}`} className="fit-team"><TeamLogo code={f.team} size={36} /><span>{th.name}</span></Link>
      <div className="fit-bar"><motion.div className="fit-bar-fill" initial={{ width: 0 }}
        animate={{ width: `${Math.max(2, (f.fit_gain / max) * 100)}%` }} transition={{ duration: 0.9, delay: i * 0.05 }} /></div>
      <span className="fit-val">{signed(f.fit_gain, 2)}</span>
      <div className="fit-tags">
        {f.own_team && <Pill>Current team</Pill>}
        {f.starter && <Pill tone="pill-accent">Starts</Pill>}
        {f.gap && f.gap !== 'Green' && <Pill tone={`pill-${f.gap.toLowerCase()}`}>Fills {f.gap_role}</Pill>}
        <Pill>{signed(f.win_pct_gain * 100, 1)} pts win %</Pill>
      </div>
    </motion.div>
  );
}

export default function PlayerFinder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: players } = useData('players');
  const [q, setQ] = useState('');
  const selected = useMemo(() => players?.find(p => p.player === (id && decodeURIComponent(id))), [players, id]);
  const best = selected?.fit?.[0];
  useTeamTheme(best ? best.team : 'IPL');

  const matches = useMemo(() => {
    if (!players || q.trim().length < 2) return [];
    const s = q.toLowerCase();
    return players.filter(p => p.has_impact && (p.display_name.toLowerCase().includes(s) || p.player.toLowerCase().includes(s))).slice(0, 8);
  }, [players, q]);
  const topPicks = useMemo(() => (players || []).filter(p => p.has_impact).sort((a, b) => b.impact - a.impact).slice(0, 12), [players]);

  const pick = p => { setQ(''); navigate(`/player/${encodeURIComponent(p.player)}`); };

  return (
    <div className="container">
      <Reveal className="page-head">
        <div className="eyebrow">Player Finder</div>
        <h1 className="display-sm">Where would he make<br />the biggest difference?</h1>
        <p className="lede">We add the player to each franchise's 2026 squad and measure how much stronger their best twelve become,
          weighted by that team's own gaps.</p>
      </Reveal>

      <div className="search glass">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search any player, e.g. Bumrah, Klaasen, Sai Sudharsan"
          aria-label="Search player" autoFocus />
        <AnimatePresence>
          {matches.length > 0 && (
            <motion.ul className="search-results" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              {matches.map(p => (
                <li key={p.player}><button onClick={() => pick(p)}>
                  <span>{p.display_name}</span><span className="muted">{p.primary_role || 'Utility'} · {p.current_team || 'Unsigned'}</span>
                </button></li>
              ))}
            </motion.ul>
          )}
        </AnimatePresence>
      </div>

      {!selected && (
        <Reveal>
          <div className="quick-picks">
            <span className="muted">Popular:</span>
            {topPicks.map(p => <button key={p.player} className="chip" onClick={() => pick(p)}>{p.display_name}</button>)}
          </div>
        </Reveal>
      )}

      <AnimatePresence mode="wait">
        {selected && (
          <motion.div key={selected.player} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}>
            <div className="player-hero glass">
              <div className="player-id">
                {selected.current_team ? <TeamLogo code={selected.current_team} size={64} /> : <div className="unsigned-badge">FA</div>}
                <div>
                  <h2>{selected.display_name}</h2>
                  <div className="muted">{selected.current_team ? theme(selected.current_team).name : 'Unsigned'} ·{' '}
                    {selected.primary_role || 'Utility'}{selected.overseas ? ' · Overseas' : ''}{selected.age_at_auction ? ` · ${Math.round(selected.age_at_auction)} yrs` : ''}</div>
                  <div className="role-pills">{roleList(selected.roles).map(r => <Pill key={r}>{r}</Pill>)}</div>
                </div>
              </div>
              <div className="stat-row compact">
                <Stat label="Impact Score" value={selected.impact} format={v => signed(v)} sub="runs/match vs average" />
                <Stat label="Fair value (2027)" value={selected.fair_value_mini_2027 ? selected.fair_value_mini_2027 / 100 : null}
                  format={v => `₹${v.toFixed(2)} cr`} sub="what his output justifies" />
                <Stat label="Likely auction price" value={selected.expected_price_mini_2027 ? selected.expected_price_mini_2027 / 100 : null}
                  format={v => `₹${v.toFixed(2)} cr`} sub="output + reputation" />
                <Stat label="Availability" value={selected.availability != null ? selected.availability * 100 : null}
                  format={v => `${v.toFixed(0)}%`} sub="team games played, 3 yrs" />
              </div>
              <PhaseBars p={selected} />
            </div>

            {best && (
              <div className="best-fit glass" style={{ '--team': theme(best.team).accent }}>
                <TeamLogo code={best.team} size={88} />
                <div>
                  <div className="eyebrow">Best fit</div>
                  <h3>{theme(best.team).name}</h3>
                  <p>
                    {best.own_team ? 'He is already in the right place: ' : ''}
                    He would {best.starter ? 'walk into their best twelve' : 'add depth'}
                    {best.gap && best.gap !== 'Green' ? `, fill their ${best.gap.toLowerCase()} ${best.gap_role.toLowerCase()} gap` : ''}
                    {' '}and lift their gap-weighted strength by {signed(best.fit_gain, 2)} (about {signed(best.win_pct_gain * 100, 1)} points
                    of win %).{!best.purse_room_now && !best.own_team ? ` They would need to release salary first (likely price ${cr(selected.expected_price_mini_2027)}).` : ''}
                  </p>
                </div>
              </div>
            )}

            <h3 className="fit-title">All ten franchises, ranked</h3>
            <div className="fit-list">
              {selected.fit.map((f, i) => <FitRow key={f.team} f={f} i={i} best={best} />)}
            </div>
            <p className="muted small-gap">Fit = rise in the team's best-12 value, weighted by its role gaps (Red x1.6, Amber x1.25) and home ground.
              Win % uses the realised-strength model (0.31 points per run/match). Purse room is checked before releases.</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
