import { useEffect, useState } from 'react';

// Static data exported by `python -m src.export_web` (web/public/data/*.json).
const cache = {};

export function loadJSON(name) {
  if (!cache[name]) {
    cache[name] = fetch(`/data/${name}.json`).then(r => {
      if (!r.ok) throw new Error(`Could not load ${name}.json`);
      return r.json();
    });
  }
  return cache[name];
}

export function useData(name) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    loadJSON(name)
      .then(data => alive && setState({ data, error: null }))
      .catch(error => alive && setState({ data: null, error }));
    return () => { alive = false; };
  }, [name]);
  return state;
}

// Live endpoints (FastAPI). Return null when the API is not running so pages
// can fall back to the pre-computed results.
export async function api(path, body) {
  try {
    const r = await fetch(`/api/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}
