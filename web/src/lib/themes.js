// Per-franchise visual themes. Colours approximate each club's public palette;
// `bends` feeds the animated ColorBends background, `accent` drives UI chrome.
export const THEMES = {
  IPL: {
    name: 'Indian Premier League', short: 'IPL',
    bends: ['#1d3fa8', '#ef4123', '#7b2ff7', '#00c2d1'],
    accent: '#5b8cff', accent2: '#ff6a3d', ink: '#ffffff', base: '#05060c',
  },
  CSK: { name: 'Chennai Super Kings', short: 'CSK', bends: ['#f9cd05', '#ffb000', '#0081e9', '#f26a21'],
    accent: '#f9cd05', accent2: '#0081e9', ink: '#111111', base: '#07090f', monogram: 'CSK' },
  DC: { name: 'Delhi Capitals', short: 'DC', bends: ['#17479e', '#2561fa', '#ef1b23', '#0d1f4f'],
    accent: '#3c7bff', accent2: '#ef1b23', ink: '#ffffff', base: '#050814', monogram: 'DC' },
  GT: { name: 'Gujarat Titans', short: 'GT', bends: ['#0b3d6b', '#c9a961', '#1565a8', '#5a4520'],
    accent: '#c9a961', accent2: '#2e6ea6', ink: '#111111', base: '#05070d', monogram: 'GT' },
  KKR: { name: 'Kolkata Knight Riders', short: 'KKR', bends: ['#3a225d', '#7b4bc4', '#d4af37', '#2a1745'],
    accent: '#b98cff', accent2: '#d4af37', ink: '#ffffff', base: '#08050f', monogram: 'KKR' },
  LSG: { name: 'Lucknow Super Giants', short: 'LSG', bends: ['#0057e2', '#00aeef', '#f47920', '#12b76a'],
    accent: '#00aeef', accent2: '#f47920', ink: '#05121f', base: '#040a14', monogram: 'LSG' },
  MI: { name: 'Mumbai Indians', short: 'MI', bends: ['#004ba0', '#0077c8', '#d1ab3e', '#00296b'],
    accent: '#2e8bff', accent2: '#d1ab3e', ink: '#ffffff', base: '#030915', monogram: 'MI' },
  PBKS: { name: 'Punjab Kings', short: 'PBKS', bends: ['#dd1f2d', '#ff4d4d', '#a7a9ac', '#7a0b14'],
    accent: '#ff3b47', accent2: '#c9cbd0', ink: '#ffffff', base: '#0d0506', monogram: 'PK' },
  RR: { name: 'Rajasthan Royals', short: 'RR', bends: ['#ea1a85', '#254aa5', '#ff7ac0', '#1b2f6e'],
    accent: '#ff3ea5', accent2: '#4c74e0', ink: '#ffffff', base: '#0b0510', monogram: 'RR' },
  RCB: { name: 'Royal Challengers Bengaluru', short: 'RCB', bends: ['#ec1c24', '#2b2a29', '#c9a227', '#8a0f14'],
    accent: '#ff2d36', accent2: '#c9a227', ink: '#ffffff', base: '#0a0505', monogram: 'RCB' },
  SRH: { name: 'Sunrisers Hyderabad', short: 'SRH', bends: ['#f26522', '#ff8a00', '#ffcc33', '#1a1a1a'],
    accent: '#ff7a1a', accent2: '#ffcc33', ink: '#111111', base: '#0c0704', monogram: 'SRH' },
};

export const TEAM_CODES = ['CSK', 'DC', 'GT', 'KKR', 'LSG', 'MI', 'PBKS', 'RR', 'RCB', 'SRH'];

export const theme = code => THEMES[code] || THEMES.IPL;
