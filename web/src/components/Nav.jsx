import { useEffect, useState } from 'react';
import { NavLink, Link, useLocation } from 'react-router-dom';
import { TEAM_CODES } from '../lib/themes';
import { TeamLogo } from './ui';

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, []);
  useEffect(() => setOpen(false), [loc.pathname]);

  return (
    <header className={`nav ${scrolled ? 'nav-scrolled' : ''}`}>
      <div className="nav-inner">
        <Link to="/" className="brand" aria-label="Auction War Room home">
          <span className="brand-ball" /> Auction War Room
        </Link>
        <nav className="nav-links">
          <NavLink to="/teams">Teams</NavLink>
          <NavLink to="/player">Player Finder</NavLink>
          <NavLink to="/market">Market</NavLink>
          <NavLink to="/method">Method</NavLink>
        </nav>
        <button className="nav-burger" aria-label="Menu" onClick={() => setOpen(o => !o)}>
          <span /><span />
        </button>
      </div>
      <div className="team-strip">
        {TEAM_CODES.map(c => (
          <NavLink key={c} to={`/team/${c}`} className="strip-team" title={c}>
            <TeamLogo code={c} size={26} /><span>{c}</span>
          </NavLink>
        ))}
      </div>
      {open && (
        <div className="nav-sheet">
          <NavLink to="/teams">Teams</NavLink>
          <NavLink to="/player">Player Finder</NavLink>
          <NavLink to="/market">Market</NavLink>
          <NavLink to="/method">Method</NavLink>
        </div>
      )}
    </header>
  );
}
