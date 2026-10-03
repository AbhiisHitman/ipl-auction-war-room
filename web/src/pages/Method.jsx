import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Reveal, useTeamTheme } from '../components/ui';

const ITEMS = [
  ['Impact Score', 'Runs a player adds per match versus a league-average player in the same phase (powerplay, middle, death) and season. Wickets are valued with a run-expectancy table: a wicket costs 12.6 runs in the powerplay, 5.8 in the middle overs and 1.8 at the death. Small samples are shrunk toward average (n / (n + 120) balls) and the last three seasons are weighted 0.5 / 0.3 / 0.2.', 'Ignores fielding, captaincy and opposition strength.'],
  ['Fair value and likely price', 'Fair value is the typical price the market pays for the same output, cap status and year (log-linear regression on 284 auction sales, 2022-26, R² 0.30). Likely price adds the previous contract as a reputation proxy (R² 0.38).', 'Prices reflect bidding dynamics; unsold players are not in the data.'],
  ['Role gaps', 'Roles come from the data (batting position, phase usage, bowling style). For each role we check whether a squad\'s k-th best player is starter quality in the league (top 10k = Green, top 15k = Amber, else Red).', 'Thresholds are judgement calls and are configurable.'],
  ['Team priorities', 'Each franchise weights roles by its own gaps (Red x1.6, Amber x1.25), how its home ground plays (spin vs pace economy, death-over scoring) and its stance (Win Now if it made the 2026 playoffs).', 'Venue effects are damped to stay within 0.85-1.20.'],
  ['Optimiser', 'An integer program (PuLP/CBC) picks the squad that maximises the value of the best twelve within the purse, 18-25 squad size, 8 overseas (4 in the XI), role minimums and the 75% minimum-spend rule. Mega-auction mode applies 2025-style retention slabs.', 'One team at a time: rivals do not react.'],
  ['Wins and revenue', 'Same-season team impact explains 53% of win %; only about 45% of a planned strength gain shows up next season. Playoff chance uses a binomial over 14 games (8 wins usually qualify) and feeds a probability-weighted franchise P&L.', 'Franchise financials are largely assumptions; see the Excel model.'],
  ['Player fit', 'For each player and franchise: how much stronger the team\'s best twelve get when he is added, using that team\'s own role weights, plus whether he would start and which gap he fills.', 'Assumes 2026 squads before any releases.'],
];

export default function Method() {
  useTeamTheme('IPL');
  const [open, setOpen] = useState(0);
  return (
    <div className="container narrow">
      <Reveal className="page-head">
        <div className="eyebrow">Methodology</div>
        <h1 className="display-sm">Simple enough to explain.<br />Rigorous enough to defend.</h1>
      </Reveal>
      <div className="accordion">
        {ITEMS.map(([t, body, lim], i) => (
          <div key={t} className={`acc glass ${open === i ? 'is-open' : ''}`}>
            <button className="acc-head" onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
              <span>{t}</span><span className="acc-icon" />
            </button>
            <AnimatePresence initial={false}>
              {open === i && (
                <motion.div className="acc-body" initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.35 }}>
                  <p>{body}</p>
                  <p className="muted"><b>Limitation:</b> {lim}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
      <Reveal>
        <p className="muted small-gap">Sources: Cricsheet ball-by-ball data (2008 - 31 May 2026), Wikipedia IPL personnel-change tables (citing ESPNcricinfo / IPLT20),
          Houlihan Lokey IPL Valuation Study 2025, published media-rights and sponsorship figures, datameet India boundary (CC BY 4.0).
          Full list in docs/sources.md; every assumption is flagged in config/assumptions.yaml.</p>
      </Reveal>
    </div>
  );
}
