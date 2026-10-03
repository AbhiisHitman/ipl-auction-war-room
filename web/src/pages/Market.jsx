import { useMemo, useState } from 'react';
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import { Reveal, Section, useTeamTheme } from '../components/ui';
import { useData } from '../lib/data';
import { pct } from '../lib/format';

const BANDS = [
  { key: 'under', label: 'Underpriced (paid < 50% of fair value)', color: '#3b82f6', test: m => m > 1 },
  { key: 'fair', label: 'Near fair value', color: '#9ca3af', test: m => m <= 1 && m >= -0.5 },
  { key: 'over', label: 'Overpriced (paid > 2x fair value)', color: '#ef4444', test: m => m < -0.5 },
];

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tip">
      <b>{d.player_name}</b> <span className="muted">'{String(d.season).slice(2)} · {d.team}</span>
      <div>Paid ₹{(d.sold_price_lakh / 100).toFixed(2)} cr · fair ₹{(d.fair_value_lakh / 100).toFixed(2)} cr</div>
      <div>Impact {d.impact.toFixed(2)} · {d.primary_role || 'no role'} · {d.phase_specialism}</div>
    </div>
  );
}

export default function Market() {
  useTeamTheme('IPL');
  const { data } = useData('market');
  const { data: meta } = useData('meta');
  const [role, setRole] = useState('All');
  const [phase, setPhase] = useState('All');
  const [season, setSeason] = useState('All');
  const [ov, setOv] = useState('All');

  const rows = useMemo(() => (data || []).filter(d =>
    (role === 'All' || d.primary_role === role) && (phase === 'All' || d.phase_specialism === phase) &&
    (season === 'All' || String(d.season) === season) &&
    (ov === 'All' || (ov === 'Overseas') === Boolean(d.overseas))
  ).map(d => ({ ...d, price: d.sold_price_lakh / 100 })), [data, role, phase, season, ov]);

  const roles = useMemo(() => ['All', ...new Set((data || []).map(d => d.primary_role).filter(Boolean))].sort(), [data]);
  const under = [...rows].sort((a, b) => b.mispricing_pct - a.mispricing_pct).slice(0, 8);
  const over = [...rows].sort((a, b) => a.mispricing_pct - b.mispricing_pct).slice(0, 8);

  const Select = ({ label, value, set, opts }) => (
    <label className="select"><span>{label}</span>
      <select value={value} onChange={e => set(e.target.value)}>{opts.map(o => <option key={o}>{o}</option>)}</select>
    </label>
  );

  return (
    <div className="container">
      <Reveal className="page-head">
        <div className="eyebrow">Market Explorer · {data?.length ?? '…'} sales, 2022-2026</div>
        <h1 className="display-sm">The market pays for the name.</h1>
        <p className="lede">Each dot is a player sold at auction. Fair value is the typical price for the same output, cap status and year.</p>
      </Reveal>

      <div className="filters glass">
        <Select label="Role" value={role} set={setRole} opts={roles} />
        <Select label="Phase specialism" value={phase} set={setPhase} opts={['All', 'Powerplay', 'Middle', 'Death']} />
        <Select label="Auction" value={season} set={setSeason} opts={['All', '2022', '2023', '2024', '2025', '2026']} />
        <Select label="Player type" value={ov} set={setOv} opts={['All', 'Overseas', 'Indian']} />
      </div>

      <div className="chart glass">
        <ResponsiveContainer width="100%" height={460}>
          <ScatterChart margin={{ top: 16, right: 24, bottom: 36, left: 8 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" />
            <XAxis type="number" dataKey="impact" name="Impact" stroke="rgba(255,255,255,0.5)"
              label={{ value: 'Impact Score at auction (runs/match vs average)', position: 'bottom', fill: 'rgba(255,255,255,0.6)' }} />
            <YAxis type="number" dataKey="price" name="Price" scale="log" domain={[0.15, 30]} allowDataOverflow
              ticks={[0.2, 0.5, 1, 2, 5, 10, 20]} stroke="rgba(255,255,255,0.5)"
              label={{ value: 'Price, ₹ crore (log)', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.6)' }} />
            <ZAxis range={[60, 60]} />
            <Tooltip content={<Tip />} cursor={{ stroke: 'rgba(255,255,255,0.2)' }} />
            {BANDS.map(b => (
              <Scatter key={b.key} name={b.label} data={rows.filter(d => b.test(d.mispricing_pct))} fill={b.color}
                fillOpacity={b.key === 'fair' ? 0.45 : 0.9} stroke="#0b0d14" strokeWidth={1.5} isAnimationActive />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
        <div className="legend">{BANDS.map(b => <span key={b.key}><i style={{ background: b.color }} />{b.label}</span>)}</div>
      </div>

      <Section eyebrow="Biggest gaps vs fair value" title="Bargains and bidding wars.">
        <div className="decision-grid">
          {[['Best value buys', under], ['Most overpaid', over]].map(([t, list]) => (
            <div key={t} className="decision glass">
              <div className="decision-head"><h3>{t}</h3></div>
              <table className="mini-table"><tbody>
                {list.map(d => (
                  <tr key={d.player_name + d.season}><td>{d.player_name} <span className="muted">'{String(d.season).slice(2)}</span></td>
                    <td>₹{d.price.toFixed(2)} cr</td><td className="muted">fair ₹{(d.fair_value_lakh / 100).toFixed(2)} cr</td></tr>
                ))}
              </tbody></table>
            </div>
          ))}
        </div>
      </Section>

      {meta && (
        <Section eyebrow="By role" title="Where the market misprices.">
          <div className="table-wrap glass">
            <table>
              <thead><tr><th>Primary role</th><th>Players</th><th>Median mispricing</th><th>Avg price</th></tr></thead>
              <tbody>{meta.mispricing_by_role.map(r => (
                <tr key={r.primary_role}><td>{r.primary_role}</td><td>{r.players}</td>
                  <td className={r.median_mispricing_pct > 0 ? 'pos' : 'neg'}>{r.median_mispricing_pct > 0 ? 'Underpriced ' : 'Overpriced '}{pct(Math.abs(r.median_mispricing_pct))}</td>
                  <td>₹{r.mean_price_cr.toFixed(1)} cr</td></tr>
              ))}</tbody>
            </table>
          </div>
          <p className="muted small-gap">Mispricing = (fair value - price) / price. Small groups (n below 8) are indicative only.</p>
        </Section>
      )}
    </div>
  );
}
