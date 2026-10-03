"""Player bio enrichment from Wikipedia infoboxes.

For every player that appears in the auction/retention records we fetch the
lead section of their Wikipedia article and read the cricketer infobox:
birth date (-> age), batting hand, bowling style (-> pace / wrist spin /
finger spin) and listed playing role. Cached in data/raw/players/.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .config import AUCTION_RAW_DIR, RAW_DIR

PLAYERS_DIR = RAW_DIR / "players"
CACHE = PLAYERS_DIR / "wiki_infobox_cache.json"
API = "https://en.wikipedia.org/w/api.php"
UA = "ipl-auction-war-room/0.1 (portfolio research project)"


def _fetch_batch(titles: list[str]) -> dict:
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
        "format": "json",
        "formatversion": "2",
        "titles": "|".join(titles),
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == 5:
                raise
            wait = float(err.headers.get("Retry-After") or 0) or 5 * 2**attempt
            time.sleep(min(wait, 120))
    raise RuntimeError("unreachable")


def fetch_infoboxes(titles: list[str]) -> dict[str, str]:
    """Return {requested title: lead wikitext}; cached so reruns are offline."""
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t and t not in cache]
    for i in range(0, len(todo), 20):
        batch = todo[i : i + 20]
        data = _fetch_batch(batch)["query"]
        # Map normalised / redirected titles back to what we asked for.
        back = {t: t for t in batch}
        for n in data.get("normalized", []):
            back[n["to"]] = back.get(n["from"], n["from"])
        for r in data.get("redirects", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for page in data.get("pages", []):
            asked = back.get(page["title"], page["title"])
            if page.get("missing"):
                cache[asked] = ""
                continue
            content = page["revisions"][0]["slots"]["main"]["content"]
            # Keep only the part before the first section heading (the infobox).
            cache[asked] = content.split("\n==", 1)[0][:20000]
        for t in batch:
            cache.setdefault(t, "")
        CACHE.write_text(json.dumps(cache))
        time.sleep(2)  # be polite to the API
    return cache


RESOLVED_CACHE = PLAYERS_DIR / "wiki_resolved_titles.json"


def resolve_titles(titles: list[str]) -> dict[str, str]:
    """Follow Wikipedia redirects: {asked title: canonical article title}.

    Different spellings of one player ('Sai Sudharshan', 'B. Sai Sudharshan')
    redirect to the same article, which gives us a stable person key."""
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, str] = json.loads(RESOLVED_CACHE.read_text()) if RESOLVED_CACHE.exists() else {}
    todo = [t for t in dict.fromkeys(titles) if t and t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i : i + 50]
        params = {"action": "query", "redirects": "1", "format": "json", "formatversion": "2",
                  "titles": "|".join(batch)}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())["query"]
        step = {t: t for t in batch}
        for n in data.get("normalized", []):
            step = {k: (n["to"] if v == n["from"] else v) for k, v in step.items()}
        for r in data.get("redirects", []):
            step = {k: (r["to"] if v == r["from"] else v) for k, v in step.items()}
        missing = {p["title"] for p in data.get("pages", []) if p.get("missing")}
        for k, v in step.items():
            cache[k] = "" if v in missing else v
        RESOLVED_CACHE.write_text(json.dumps(cache))
        time.sleep(1)
    return cache


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"^[ \t]*\|[ \t]*{name}[ \t]*=[ \t]*(.*)$", text, flags=re.M | re.I)
    if not m:
        return None
    val = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", m.group(1))
    val = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", val)
    # List templates ({{ubl|a|b}}, {{hlist|...}}) keep their items.
    val = re.sub(r"\{\{\s*(?:ubl|hlist|unbulleted list|plainlist|flatlist|nowrap)\s*\|([^{}]*)\}\}",
                 lambda t: t.group(1).replace("|", "; "), val, flags=re.I)
    val = re.sub(r"\{\{[^{}]*\}\}", lambda t: t.group(0) if "birth" in t.group(0).lower() else "", val)
    val = val.replace("}}", "").replace("{{", "")
    return val.strip() or None


def _birth_date(text: str) -> pd.Timestamp | None:
    m = re.search(r"\{\{\s*birth[ _]date(?:[ _]and[ _]age)?\s*\|([^}]*)\}\}", text, flags=re.I)
    if not m:
        return None
    nums = [p.strip() for p in m.group(1).split("|") if re.fullmatch(r"\s*\d+\s*", p)]
    if len(nums) >= 3:
        try:
            return pd.Timestamp(int(nums[0]), int(nums[1]), int(nums[2]))
        except ValueError:
            return None
    return None


def bowling_type(style: str | None) -> str | None:
    """Collapse an infobox bowling style into pace / wrist_spin / finger_spin."""
    if not style:
        return None
    s = style.lower()
    keys = {
        "wrist_spin": ("leg break", "legbreak", "leg-break", "googly", "leg spin", "leg-spin",
                       "wrist", "unorthodox", "chinaman"),
        "finger_spin": ("off break", "offbreak", "off-break", "off spin", "off-spin",
                        "orthodox", "slow left"),
        "pace": ("fast", "medium", "seam", "pace"),
    }
    # Multi-style bowlers: the style listed FIRST in the infobox is the primary one.
    # ('unorthodox' is matched before 'orthodox' because find() returns the earlier hit.)
    best: tuple[int, str] | None = None
    for kind, words in keys.items():
        for w in words:
            pos = s.find(w)
            if pos >= 0 and (best is None or pos < best[0]):
                best = (pos, kind)
    return best[1] if best else None


def parse_bio(text: str) -> dict:
    return {
        "birth_date": _birth_date(text),
        "batting_hand": _field(text, "batting"),
        "bowling_style": _field(text, "bowling"),
        "wiki_role": _field(text, "role"),
        "bowling_type": bowling_type(_field(text, "bowling")),
        # Any international debut in the infobox = capped (for retention rules).
        "capped_intl": any(_field(text, f) for f in ("testdebutdate", "odidebutdate", "T20Idebutdate",
                                                     "testdebutyear", "odidebutyear", "T20Idebutyear")),
    }


def add_person_key(auction: pd.DataFrame) -> pd.DataFrame:
    """Add `person` (canonical Wikipedia article, or the cleaned name when no
    article exists) and `display_name` (the most recent spelling we saw)."""
    out = auction.copy()
    asked = out["wiki_title"].fillna(out["player_name"])
    resolved = resolve_titles(asked.tolist())
    def key(title: str, name: str) -> str:
        r = resolved.get(title) or ""
        # Some table links point at a team/season page instead of the player;
        # accept the article only if it shares a word with the player's name.
        base = set(re.sub(r"\(.*?\)", "", r).lower().replace(".", " ").split())
        if r and base & set(name.lower().replace(".", " ").split()):
            return r
        return name

    out["person"] = [key(t, n) for t, n in zip(asked, out["player_name"])]
    # 'Abdul Samad' and 'Abdul Samad (Indian cricketer)' are one person: prefer
    # the more specific (disambiguated) article when the base names agree.
    stripped = out["person"].str.replace(r"\s*\(.*\)$", "", regex=True)
    specific = (out.assign(s=stripped)[out["person"].str.contains(r"\(", regex=True)]
                .groupby("s")["person"].first())
    out["person"] = [specific.get(s, p) for s, p in zip(stripped, out["person"])]
    aliases_path = AUCTION_RAW_DIR / "person_aliases.csv"
    if aliases_path.exists():
        aliases = pd.read_csv(aliases_path).set_index("alias")["person"]
        out["person"] = out["person"].replace(aliases.to_dict())
    latest = out.sort_values("season").groupby("person")["player_name"].last()
    out["display_name"] = out["person"].map(latest)
    return out


def build_player_bios(auction: pd.DataFrame) -> pd.DataFrame:
    """One bio row per person (requires `person` from add_person_key)."""
    people = auction.drop_duplicates("person")[["person", "display_name"]]
    cache = fetch_infoboxes(people["person"].tolist())
    rows = []
    for person, name in people.itertuples(index=False):
        text = cache.get(person, "")
        bio = parse_bio(text)
        bio.update({"person": person, "display_name": name, "wiki_found": bool(text)})
        rows.append(bio)
    bios = pd.DataFrame(rows)
    bios.to_csv(PLAYERS_DIR / "player_bios.csv", index=False)
    return bios


if __name__ == "__main__":
    from .ingest import load_auction

    from .wiki_auction import build_auction_records

    a = add_person_key(build_auction_records())
    b = build_player_bios(a)
    print(a["player_name"].nunique(), "spellings ->", a["person"].nunique(), "people")
    print(len(b), "players;", b.wiki_found.mean().round(3), "found;",
          b.birth_date.notna().mean().round(3), "with birth date")
    print(b.bowling_type.value_counts(dropna=False))
