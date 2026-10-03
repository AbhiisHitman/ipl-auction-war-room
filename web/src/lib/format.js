export const cr = lakh => (lakh == null ? '—' : `₹${(lakh / 100).toFixed(lakh >= 1000 ? 1 : 2)} cr`);
export const crv = v => (v == null ? '—' : `₹${Number(v).toFixed(v >= 10 ? 1 : 2)} cr`);
export const pct = (v, d = 0) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
export const signed = (v, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${Number(v).toFixed(d)}`);
export const ordinal = n => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
export const roleList = r => (Array.isArray(r) ? r : String(r || '').split(';').filter(Boolean));
export const MODE_LABEL = { mini_2027: 'IPL 2027 Mini-auction', mega_2028: 'IPL 2028 Mega-auction' };

// Backend text uses 'Rs'; show the rupee sign in the UI.
export const rupee = s => (s == null ? s : String(s).replaceAll('Rs ', '₹'));
