import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { CoverageGrid, Pill, Reveal, Section, Stat, TeamLogo, useTeamTheme } from '../components/ui';
import { api, useData } from '../lib/data';
import DeckViewer from '../components/DeckViewer';
import { theme, TEAM_CODES } from '../lib/themes';
import { MODE_LABEL, crv, cr, ordinal, pct, roleList, rupee, signed } from '../lib/format';

function ModeSwitch({ mode, setMode }) {
  return (
    <div className="segmented" role="tablist" aria-label="Auction type">
      {Object.entries(MODE_LABEL).map(([k, v]) => (
        <button key={k} role="tab" aria-selected={mode === k} className={mode === k ? 'is-on' : ''} onClick={() => setMode(k)}>
          {mode === k && <motion.span layoutId="seg" className="seg-bg" transition={{ type: 'spring', stiffness: 400, damping: 34 }} />}
          <span className="seg-txt">{v}</span>
        </button>
      ))}
    </div>
  );
}

function TargetCard({ r, i }) {
  return (
    <motion.article className="target glass" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }} transition={{ delay: Math.min(i, 6) * 0.05, duration: 0.6 }}>
      <div className="target-top">
        <div>
          <div className="target-name">{r.player}</div>
          <div className="target-role">{r.role || 'Utility'}{r.overseas ? ' · Overseas' : ''}{r.age ? ` · ${Math.round(r.age)} yrs` : ''}</div>
        </div>
        <div className="target-tags">
          {r.starter && <Pill tone="pill-accent">Starter</Pill>}
          {r.gap_filled && r.gap_filled !== 'Green' && <Pill tone={`pill-${r.gap_filled.toLowerCase()}`}>Fixes {r.gap_filled}</Pill>}
          {r.action === 'Buy back' && <Pill>Buy back</Pill>}
        </div>
      </div>
      <div className="target-nums">
        <div><span>Impact</span><b>{signed(r.impact_score)}</b></div>
        <div><span>Fair value</span><b>{crv(r.fair_value_cr)}</b></div>
        <div><span>Likely price</span><b>{crv(r.expected_cost_cr)}</b></div>
        <div className="ceiling"><span>Bid ceiling</span><b>{crv(r.bid_ceiling_cr)}</b></div>
      </div>
      <p className="target-why">{rupee(r.rationale)}</p>
      <p className="target-risk"><span>Risk</span>{rupee(r.risk)}</p>
      {r.backup_option && <p className="target-backup"><span>Backup</span>{rupee(r.backup_option)}</p>}
    </motion.article>
  );
}

function DecisionList({ title, rows, tone }) {
  return (
    <div className="decision glass">
      <div className="decision-head"><h3>{title}</h3><Pill tone={tone}>{rows.length}</Pill></div>
      <ul>
        {rows.map(r => (
          <li key={r.cricsheet_name}>
            <div className="decision-row">
              <span className="decision-name">{r.player}</span>
              <span className="decision-imp">{signed(r.impact_score)}</span>
            </div>
            <div className="decision-why">{rupee(r.rationale)}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RoleOptions({ role, code, players, mode }) {
  const list = useMemo(() => {
    if (!players || !role) return [];
    return players
      .filter(p => p.has_impact && roleList(p.roles).includes(role) && p.current_team !== code &&
        (mode === 'mega_2028' || !p.current_team || p.projected_release))
      .map(p => ({ ...p, f: p.fit.find(x => x.team === code) }))
      .sort((a, b) => (b.f?.fit_gain ?? 0) - (a.f?.fit_gain ?? 0))
      .slice(0, 6);
  }, [players, role, code, mode]);
  if (!role) return null;
  return (
    <motion.div className="role-options glass" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
      <div className="role-options-head">Best market options for <b>{role}</b>{mode === 'mini_2027' ? ' (unsigned or likely released)' : ''}</div>
      {list.length === 0 && <div className="muted">No available players hold this role.</div>}
      <div className="role-options-grid">
        {list.map(p => (
          <Link key={p.player} to={`/player/${encodeURIComponent(p.player)}`} className="role-option">
            <span className="ro-name">{p.display_name}</span>
            <span className="ro-meta">{signed(p.impact)} impact · ~{cr(p[`expected_price_${mode}`])}{p.current_team ? ` · ${p.current_team}` : ' · unsigned'}</span>
          </Link>
        ))}
      </div>
    </motion.div>
  );
}

function Simulator({ code, mode, base, squad }) {
  const [strategy, setStrategy] = useState(base?.strategy || 'win_now');
  const [infl, setInfl] = useState(0.1);
  const [locked, setLocked] = useState([]);
  const [excluded, setExcluded] = useState([]);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => { setRes(null); setStrategy(base?.strategy || 'win_now'); }, [code, mode, base]);

  const run = async () => {
    setBusy(true);
    const out = await api('optimise', { team: code, mode, strategy, rival_inflation: infl, locked, excluded });
    setBusy(false);
    if (!out) { setOffline(true); return; }
    setOffline(false);
    setRes(out);
  };
  const s = res?.summary || base;
  const toggle = (arr, set, v) => set(arr.includes(v) ? arr.filter(x => x !== v) : [...arr, v]);

  return (
    <div className="sim">
      <div className="sim-controls glass">
        <label className="field">
          <span>Strategy</span>
          <div className="segmented small">
            {[['win_now', 'Win Now'], ['long_term', 'Long-Term Build']].map(([k, v]) => (
              <button key={k} className={strategy === k ? 'is-on' : ''} onClick={() => setStrategy(k)}>
                {strategy === k && <motion.span layoutId="seg2" className="seg-bg" />}<span className="seg-txt">{v}</span>
              </button>
            ))}
          </div>
        </label>
        <label className="field">
          <span>Rival bidding inflation: <b>+{Math.round(infl * 100)}%</b></span>
          <input type="range" min="0" max="0.5" step="0.05" value={infl} onChange={e => setInfl(+e.target.value)} />
        </label>
        <div className="field">
          <span>Own squad: lock in or force out</span>
          <div className="chip-wrap">
            {squad.slice(0, 18).map(p => {
              const state = locked.includes(p.player) ? 'lock' : excluded.includes(p.player) ? 'out' : '';
              return (
                <button key={p.player} className={`chip ${state}`} title="Click: lock in · Alt-click: force out"
                  onClick={e => (e.altKey ? toggle(excluded, setExcluded, p.player) : toggle(locked, setLocked, p.player))}>
                  {p.display_name}{state === 'lock' ? ' · locked' : state === 'out' ? ' · out' : ''}
                </button>
              );
            })}
          </div>
          <small className="muted">Click to lock a player in; Alt-click to force him out.</small>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? 'Optimising…' : 'Run optimiser'}</button>
        {offline && <div className="notice">Live optimiser is offline (start the API). Showing the pre-computed plan.</div>}
      </div>
      <div className="sim-results">
        <div className="stat-row compact">
          <Stat label="Purse used" value={s?.purse_used_cr} format={v => `₹${v.toFixed(1)} cr`} sub={`of ₹${s?.purse_total_cr ?? 125} cr`} />
          <Stat label="Squad strength" value={s?.strength_after} format={v => v.toFixed(1)} sub={`from ${s?.strength_before?.toFixed(1)} today`} />
          <Stat label="Playoff chance" value={s ? s.playoff_prob_after * 100 : null} format={v => `${v.toFixed(0)}%`}
            sub={`from ${pct(s?.playoff_prob_before)} today`} />
          <Stat label="Expected profit change" value={s ? s.exp_profit_after_cr - s.exp_profit_before_cr : null}
            format={v => `${v >= 0 ? '+' : ''}₹${v.toFixed(1)} cr`} sub="probability-weighted" />
        </div>
        <AnimatePresence>
          {res && (
            <motion.div className="sim-buys glass" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
              <h4>Optimised plan · {res.summary.buys} buys, {res.summary.releases} releases, solved in {res.summary.solve_seconds}s</h4>
              <div className="sim-buy-list">
                {res.recommendations.filter(r => r.action !== 'Release').map(r => (
                  <div key={r.cricsheet_name} className={`sim-buy act-${r.action.replace(' ', '-')}`}>
                    <span>{r.player}</span><span className="muted">{r.action} · {r.role || 'Utility'} · {crv(r.expected_cost_cr)}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Economics({ code, team }) {
  const base = team.economics;
  const [ticket, setTicket] = useState(base.inputs.avg_ticket_price_inr);
  const [occ, setOcc] = useState(base.inputs.occupancy);
  const [spons, setSpons] = useState(base.inputs.team_sponsorship_base_cr);
  const [pPlay, setPPlay] = useState(team.summary.find(s => s.mode === 'mini_2027')?.playoff_prob_before ?? 0.5);
  const [out, setOut] = useState(null);
  useEffect(() => {
    const id = setTimeout(async () => {
      const r = await api('economics', { team: code, p_playoffs: pPlay,
        overrides: { avg_ticket_price_inr: ticket, occupancy: occ, team_sponsorship_base_cr: spons } });
      setOut(r);
    }, 180);
    return () => clearTimeout(id);
  }, [code, ticket, occ, spons, pPlay]);
  const table = out?.table || base.table;
  const line = n => table.find(r => r.line === n) || {};
  const rows = ['Central media rights share', 'Central sponsorship share', 'Team sponsorships', 'Ticketing (home matches)',
    'Merchandise', 'Prize money', 'Total revenue', 'Total operating costs', 'Operating profit', 'Profit after franchise fee'];
  const mix = line('Central (fixed) share of revenue').missed_playoffs;
  return (
    <div className="econ">
      <div className="econ-controls glass">
        <label className="field"><span>Average ticket price: <b>₹{ticket.toLocaleString('en-IN')}</b></span>
          <input type="range" min="1000" max="6000" step="100" value={ticket} onChange={e => setTicket(+e.target.value)} /></label>
        <label className="field"><span>Stadium occupancy: <b>{Math.round(occ * 100)}%</b></span>
          <input type="range" min="0.5" max="1" step="0.01" value={occ} onChange={e => setOcc(+e.target.value)} /></label>
        <label className="field"><span>Team sponsorship (avg brand): <b>₹{spons} cr</b></span>
          <input type="range" min="30" max="150" step="5" value={spons} onChange={e => setSpons(+e.target.value)} /></label>
        <label className="field"><span>Chance of making playoffs: <b>{Math.round(pPlay * 100)}%</b></span>
          <input type="range" min="0" max="1" step="0.01" value={pPlay} onChange={e => setPPlay(+e.target.value)} /></label>
        {out ? (
          <div className="econ-expected">
            <div><span>Expected revenue</span><b>₹{out.expected.expected_revenue_cr.toFixed(0)} cr</b></div>
            <div><span>Expected operating profit</span><b>₹{out.expected.expected_profit_cr.toFixed(0)} cr</b></div>
          </div>
        ) : <div className="notice">Sliders need the API; showing the default case.</div>}
      </div>
      <div className="econ-table glass">
        <div className="econ-mix">{pct(mix)} of revenue is fixed central income.</div>
        <table>
          <thead><tr><th>₹ crore / season</th><th>Missed playoffs</th><th>Made playoffs</th><th>Won title</th></tr></thead>
          <tbody>
            {rows.map(n => {
              const r = line(n);
              const strong = /Total|profit/i.test(n);
              return (
                <tr key={n} className={strong ? 'strong' : ''}>
                  <td>{n}</td>
                  {['missed_playoffs', 'made_playoffs', 'won_title'].map(k => <td key={k}>{r[k] == null ? '—' : r[k].toFixed(1)}</td>)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Team() {
  const { code: raw } = useParams();
  const code = TEAM_CODES.includes(raw?.toUpperCase()) ? raw.toUpperCase() : 'CSK';
  useTeamTheme(code);
  const th = theme(code);
  const { data: teams } = useData('teams');
  const { data: players } = useData('players');
  const [mode, setMode] = useState('mini_2027');
  const [role, setRole] = useState(null);
  useEffect(() => setRole(null), [code]);

  const team = teams?.[code];
  if (!team) return <div className="container loading">Loading war room…</div>;
  const b = team.brief;
  const summary = team.summary.find(s => s.mode === mode);
  const recs = team.recommendations[mode];
  const buys = recs.filter(r => r.action === 'Buy' || r.action === 'Buy back');
  const retain = recs.filter(r => r.action === 'Retain');
  const release = recs.filter(r => r.action === 'Release');
  const scen = team.scenarios.filter(s => s.mode === mode);
  const idx = TEAM_CODES.indexOf(code);
  const next = TEAM_CODES[(idx + 1) % TEAM_CODES.length];

  return (
    <div className="team-page">
      <section className="team-hero">
        <motion.div className="team-hero-logo" initial={{ opacity: 0, scale: 0.8, rotate: -6 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}>
          <TeamLogo code={code} size={150} />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.9 }}>
          <div className="eyebrow">{b.home_venue} · finished {ordinal(b.finish_2026)} in 2026</div>
          <h1 className="display-sm">{th.name}</h1>
          <p className="lede"><Pill tone={b.stance === 'Win Now' ? 'pill-win' : 'pill-build'}>{b.stance}</Pill> {b.stance_reason}</p>
          <div className="hero-ctas left">
            <a href="#downloads" className="btn btn-primary">View and download the deck</a>
          </div>
        </motion.div>
        <div className="stat-row">
          <Stat label="Purse left before releases" value={b.purse_left_cr} format={v => `₹${v.toFixed(1)} cr`} sub="of ₹125 cr (2027, assumed)" />
          <Stat label="Overseas slots open" value={b.overseas_slots_left} format={v => v.toFixed(0)} sub="max 8 in squad" />
          <Stat label="Core age (top 12)" value={b.core_age} format={v => v.toFixed(1)} />
          <Stat label="Playoff chance after plan" value={summary ? summary.playoff_prob_after * 100 : null}
            format={v => `${v.toFixed(0)}%`} sub={summary ? `today ${pct(summary.playoff_prob_before)}` : ''} />
        </div>
      </section>

      <div className="container">
        {/* The mode toggle stays pinned only while the mode-dependent sections are on screen. */}
        <div className="mode-scope">
        <div className="sticky-bar"><ModeSwitch mode={mode} setMode={setMode} /></div>
        <Section eyebrow="Priorities" title={`What ${th.short} must fix first.`}>
          <div className="prio-wrap">
            <ol className="prio-list">
              {b.priorities.length === 0 && <li>No red or amber gaps: protect the core and buy depth.</li>}
              {b.priorities.map((p, i) => <Reveal as="li" key={i} delay={i * 0.06}>{p}</Reveal>)}
            </ol>
          </div>
          <Reveal><p className="muted small-gap">Select a role to see the best available players for it.</p></Reveal>
          <CoverageGrid rows={team.coverage} onPick={r => setRole(role === r ? null : r)} active={role} />
          <AnimatePresence>{role && <RoleOptions role={role} code={code} players={players} mode={mode} />}</AnimatePresence>
        </Section>

        <Section eyebrow={`${MODE_LABEL[mode]} · targets`} title="Who to bid for, and the price to walk away at.">
          <div className="target-grid">
            {buys.map((r, i) => <TargetCard key={r.cricsheet_name} r={r} i={i} />)}
          </div>
        </Section>

        <Section eyebrow="Squad decisions" title="Keep the value. Free the purse.">
          <div className="decision-grid">
            <DecisionList title="Retain" rows={retain} tone="pill-win" />
            <DecisionList title="Release" rows={release} tone="pill-red" />
          </div>
        </Section>

        <Section eyebrow="Auction simulator" title="Change the plan. Watch it re-optimise.">
          <Simulator code={code} mode={mode} base={summary} squad={team.squad} />
        </Section>

        {scen.length > 0 && (
          <Section eyebrow="Scenarios" title="How the plan holds up when rivals bid harder.">
            <div className="table-wrap glass">
              <table>
                <thead><tr><th>Scenario</th><th>Purse used</th><th>Buys</th><th>Strength</th><th>Playoff chance</th></tr></thead>
                <tbody>
                  {scen.map(s => (
                    <tr key={s.scenario}><td>{s.scenario}</td><td>₹{s.purse_used_cr.toFixed(1)} cr</td><td>{s.buys}</td>
                      <td>{s.strength_after.toFixed(1)}</td><td>{pct(s.playoff_prob_after)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        </div>

        <Section eyebrow="Franchise economics" title="What a deep run is actually worth.">
          <Economics code={code} team={team} />
        </Section>

        <Section id="downloads" eyebrow="Downloads" title="Take it to the boardroom.">
          <DeckViewer code={code} teamName={th.name} />
        </Section>

        <Reveal>
          <Link to={`/team/${next}`} className="next-team glass">
            <span className="muted">Next war room</span>
            <span className="next-team-name"><TeamLogo code={next} size={40} />{theme(next).name} →</span>
          </Link>
        </Reveal>
      </div>
    </div>
  );
}
