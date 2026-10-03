"""Compile auction + retention records from Wikipedia wikitext.

Source pages: "List of <YEAR> Indian Premier League personnel changes"
(fetched as raw wikitext into data/raw/auction/wiki/). Wikipedia in turn cites
ESPNcricinfo / IPLT20.com for every table - see docs/sources.md.

Output schema (data/raw/auction/auction_records.csv):
    season, player_name, wiki_title, team, role, nationality, overseas, capped,
    base_price_lakh, sold_price_lakh, status (sold / retained), ipl_matches, set_name

`season` is the IPL season the contract is for (the Dec-2025 auction -> 2026).
Unsold players are NOT listed on these pages; see docs/methodology.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import AUCTION_RAW_DIR
from .teams import team_code

WIKI_DIR = AUCTION_RAW_DIR / "wiki"
SEASONS = [2022, 2023, 2024, 2025, 2026]
MEGA_AUCTION_SEASONS = {2022, 2025}


# --------------------------------------------------------------------------
# Low-level wikitext helpers
# --------------------------------------------------------------------------
def _split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` only outside {{templates}} and [[links]]."""
    out, depth, buf, i = [], 0, [], 0
    while i < len(text):
        two = text[i : i + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
            continue
        if depth == 0 and text.startswith(sep, i):
            out.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(text[i])
        i += 1
    out.append("".join(buf))
    return out


def _strip_attrs(cell: str) -> tuple[str, dict[str, str]]:
    """'rowspan="2" | value' -> ('value', {'rowspan': '2'})."""
    parts = _split_top(cell, "|")
    if len(parts) >= 2 and re.search(r'^\s*[\w-]+\s*=', parts[0]) and "{{" not in parts[0]:
        attrs = dict(re.findall(r'([\w-]+)\s*=\s*"?([^"\s]+)"?', parts[0]))
        return "|".join(parts[1:]), attrs
    return cell, {}


def _remove_refs(text: str) -> str:
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    return text


def _template_args(tpl: str) -> tuple[str, list[str], dict[str, str]]:
    inner = tpl[2:-2]
    parts = _split_top(inner, "|")
    name = parts[0].strip().lower()
    pos, kw = [], {}
    for p in parts[1:]:
        if re.match(r"^\s*[\w-]+\s*=", p) and "[[" not in p.split("=")[0]:
            k, v = p.split("=", 1)
            kw[k.strip()] = v.strip()
        else:
            pos.append(p.strip())
    return name, pos, kw


@dataclass
class Cell:
    text: str  # plain display text
    link: str | None = None  # wiki article title (for player enrichment)
    country: str | None = None
    lakh: float | None = None  # money converted to lakh


def parse_cell(raw: str) -> Cell:
    raw = _remove_refs(raw).strip()
    cell = Cell(text="")
    # Money templates: {{INRConvert|18|c}} = 18 crore; {{INRConvert|30|l}} = 30 lakh.
    m = re.search(r"\{\{INRConvert\|([\d.,]+)\|(\w)", raw)
    if m:
        val = float(m.group(1).replace(",", ""))
        cell.lakh = val * 100 if m.group(2).lower() == "c" else val
    else:
        m = re.search(r"₹\s*([\d.,]+)\s*(crore|lakh)", raw, flags=re.I)
        if m:
            val = float(m.group(1).replace(",", ""))
            cell.lakh = val * 100 if m.group(2).lower() == "crore" else val
    # Country flags
    m = re.search(r"\{\{(?:cr|cricon|flagicon|flagathlete)\|([^|}]+)", raw)
    if m:
        c = m.group(1).strip().upper()
        cell.country = "IND" if c in ("IND", "INDIA") else c
    # Player name templates
    m = re.search(r"\{\{sortname\|[^{}]*\}\}", raw)
    if m:
        _, pos, kw = _template_args(m.group(0))
        first, last = pos[0], pos[1] if len(pos) > 1 else ""
        display = f"{first} {last}".strip()
        target = pos[2] if len(pos) > 2 and pos[2] else display
        if "dab" in kw:
            target = f"{display} ({kw['dab']})"
        cell.text, cell.link = display, target
        if "nolink" in kw:
            cell.link = None
        return cell
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", raw)
    text = raw
    if m:
        cell.link = m.group(1).strip()
        text = raw.replace(m.group(0), (m.group(2) or m.group(1)))
    text = re.sub(r"\{\{(?:N/?A|n/a|N/a|N\/a)\}\}", "", text, flags=re.I)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("'''", "").replace("''", "")
    cell.text = re.sub(r"\s+", " ", text).strip()
    return cell


@dataclass
class Table:
    heading: str
    caption: str
    headers: list[str]
    rows: list[list[Cell]] = field(default_factory=list)
    row_context: list[str | None] = field(default_factory=list)  # e.g. team from colspan rows


def parse_tables(wikitext: str) -> list[Table]:
    """Minimal wikitable parser with rowspan support."""
    tables: list[Table] = []
    heading = ""
    lines = wikitext.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        hm = re.match(r"^(=+)\s*(.*?)\s*\1$", line)
        if hm:
            heading = hm.group(2)
        if not line.startswith("{|"):
            i += 1
            continue
        tbl = Table(heading=heading, caption="", headers=[])
        current: list[tuple[str, dict]] = []
        pending_span: dict[int, tuple[Cell, int]] = {}
        context: str | None = None
        seen_data = False

        def flush() -> None:
            nonlocal current, context, seen_data
            if not current:
                return
            cells_raw = current
            current = []
            # A header block (all '!' cells before any data row)
            if all(kind == "!" for kind, _ in cells_raw) and not seen_data and not tbl.headers:
                if any(a.get("colspan") for _, (t, a) in [(k, _strip_attrs(c)) for k, c in cells_raw]) and len(cells_raw) == 1:
                    pass
                else:
                    tbl.headers = [parse_cell(_strip_attrs(c)[0]).text for _, c in cells_raw]
                    return
            # Single-cell spanning row = section marker (team name / set name)
            if len(cells_raw) == 1:
                txt, attrs = _strip_attrs(cells_raw[0][1])
                if attrs.get("colspan"):
                    context = parse_cell(txt).text
                    return
            seen_data = True
            row: list[Cell] = []
            col = 0
            queue = [(_strip_attrs(c)) for _, c in cells_raw]
            q = 0
            while q < len(queue) or col in pending_span:
                if col in pending_span:
                    cell, left = pending_span[col]
                    row.append(cell)
                    if left <= 1:
                        del pending_span[col]
                    else:
                        pending_span[col] = (cell, left - 1)
                    col += 1
                    continue
                txt, attrs = queue[q]
                q += 1
                cell = parse_cell(txt)
                span = int(attrs.get("rowspan", "1") or 1)
                for _ in range(int(attrs.get("colspan", "1") or 1)):
                    if span > 1:
                        pending_span[col] = (cell, span - 1)
                    row.append(cell)
                    col += 1
            tbl.rows.append(row)
            tbl.row_context.append(context)

        i += 1
        while i < len(lines):
            line = lines[i].rstrip()
            s = line.strip()
            if s.startswith("|}"):
                flush()
                break
            if s.startswith("|+"):
                tbl.caption = parse_cell(_remove_refs(s[2:])).text
                cap_link = parse_cell(_remove_refs(s[2:])).link
                if cap_link:
                    tbl.caption = cap_link
            elif s.startswith("|-"):
                flush()
            elif s.startswith("!"):
                for c in _split_top(s[1:], "!!"):
                    for c2 in _split_top(c, "||"):
                        current.append(("!", c2))
            elif s.startswith("|"):
                for c in _split_top(s[1:], "||"):
                    current.append(("|", c))
            elif current:  # continuation of previous cell
                kind, prev = current[-1]
                current[-1] = (kind, prev + " " + s)
            i += 1
        tables.append(tbl)
        i += 1
    return tables


# --------------------------------------------------------------------------
# Domain mapping
# --------------------------------------------------------------------------
def _norm_header(h: str, season: int) -> str:
    h = h.lower()
    if "auction" in h and "price" in h:
        return "sold_price"
    if "base" in h:
        return "base_price"
    if h in ("name", "player"):
        return "name"
    if h in ("country", "nationality"):
        return "country"
    if "role" in h:
        return "role"
    if "matches" in h:
        return "ipl_matches"
    if "capped" in h or h == "category":
        return "capped"
    if "salary" in h:
        return "salary"
    if "team" in h and str(season) in h:
        return "team"
    if h == "set":
        return "set"
    return h


def _try_team(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return team_code(text)
    except KeyError:
        return None


def _number(cell: Cell) -> float | None:
    if cell.lakh is not None:
        return cell.lakh
    t = cell.text.replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def records_for_season(season: int) -> pd.DataFrame:
    text = (WIKI_DIR / f"personnel_{season}.wiki").read_text(encoding="utf-8")
    out: list[dict] = []
    for tbl in parse_tables(text):
        heads = [_norm_header(h, season) for h in tbl.headers]
        heading = tbl.heading.lower()
        is_sold = "sold" in heading
        is_retained = ("retain" in heading or "retention" in heading) and "salary" in heads
        if not (is_sold or is_retained) or "name" not in heads and "player" not in heads:
            continue
        name_idx = heads.index("name")
        for row, ctx in zip(tbl.rows, tbl.row_context):
            if len(row) < len(heads):  # trailing empty cells are often omitted
                row = row + [Cell(text="")] * (len(heads) - len(row))
            rec = {h: row[k] for k, h in enumerate(heads)}
            name_cell = row[name_idx]
            if not name_cell.text:
                continue
            # '(REP)' = replacement signing, '(T)' = traded; same player either way.
            name_cell.text = re.sub(r"\s*\((?:REP|T|R|RTM)\)\s*$", "", name_cell.text).strip()
            country = rec.get("country").country if rec.get("country") else None
            if is_sold:
                team = (_try_team(rec["team"].text) or _try_team(rec["team"].link)) if "team" in rec else None
                price = _number(rec["sold_price"]) if "sold_price" in rec else None
                if team is None or price is None:
                    continue  # unsold rows (if any) are skipped
                capped_txt = rec["capped"].text.lower() if "capped" in rec else ""
                set_name = tbl.caption or (ctx or "")
                if not capped_txt:
                    capped_txt = "uncapped" if "uncapped" in set_name.lower() else "capped"
                out.append(
                    {
                        "season": season,
                        "player_name": name_cell.text,
                        "wiki_title": name_cell.link,
                        "team": team,
                        "role": rec["role"].text if "role" in rec else _role_from_set(set_name),
                        "nationality": country,
                        "capped": "uncapped" not in capped_txt,
                        "base_price_lakh": _number(rec["base_price"]) if "base_price" in rec else None,
                        "sold_price_lakh": price,
                        "status": "sold",
                        "ipl_matches": _number(rec["ipl_matches"]) if "ipl_matches" in rec else None,
                        "set_name": set_name,
                    }
                )
            else:
                team = _try_team(tbl.caption) or _try_team(ctx)
                salary = _number(rec["salary"])
                if team is None:
                    continue
                out.append(
                    {
                        "season": season,
                        "player_name": name_cell.text,
                        "wiki_title": name_cell.link,
                        "team": team,
                        "role": None,
                        "nationality": country,
                        "capped": None,
                        "base_price_lakh": None,
                        "sold_price_lakh": salary,
                        "status": "retained",
                        "ipl_matches": None,
                        "set_name": "retained",
                    }
                )
    df = pd.DataFrame(out)
    df["overseas"] = df["nationality"].ne("IND")
    df["mega_auction"] = season in MEGA_AUCTION_SEASONS
    return df


def _role_from_set(set_name: str) -> str | None:
    s = set_name.lower()
    for key, role in [
        ("wicket", "Wicket-keeper"),
        ("all-round", "All-rounder"),
        ("fast", "Fast bowler"),
        ("spin", "Spin bowler"),
        ("batter", "Batter"),
    ]:
        if key in s:
            return role
    return None


def normalise_role(raw: str | None) -> str | None:
    """Collapse Wikipedia's role spellings to five labels."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).lower()
    if "wicket" in s or "keeper" in s:
        return "Wicket-keeper"
    if "all" in s:
        return "All-rounder"
    if "spin" in s:
        return "Spin bowler"
    if "fast" in s or "pace" in s or "bowler" in s:
        return "Fast bowler"
    if "bat" in s:
        return "Batter"
    return None


def build_auction_records() -> pd.DataFrame:
    df = pd.concat([records_for_season(s) for s in SEASONS], ignore_index=True)
    df["role"] = df["role"].map(normalise_role)
    # Harmonise country codes, then fill gaps from the same player's other
    # seasons, then from the small manual override file.
    df["nationality"] = df["nationality"].replace(
        {"WEST INDIES": "WIN", "WI": "WIN", "RSA": "SA", "AUSTRALIA": "AUS", "IRELAND": "IRE", "NAMIBIA": "NAM", "BANGLADESH": "BAN"}
    )
    known = df.dropna(subset=["nationality"]).groupby("player_name")["nationality"].first()
    df["nationality"] = df["nationality"].fillna(df["player_name"].map(known))
    overrides = pd.read_csv(AUCTION_RAW_DIR / "nationality_overrides.csv").set_index("player_name")["nationality"]
    df["nationality"] = df["nationality"].fillna(df["player_name"].map(overrides))
    df["overseas"] = df["nationality"].ne("IND")
    df["role"] = df["role"].fillna(df["player_name"].map(df.dropna(subset=["role"]).groupby("player_name")["role"].last()))
    df = df.drop_duplicates(["season", "player_name", "team", "status"])
    path = AUCTION_RAW_DIR / "auction_records.csv"
    df.to_csv(path, index=False)
    return df


if __name__ == "__main__":
    recs = build_auction_records()
    print(recs.groupby(["season", "status"]).size().unstack())
    print(recs.groupby(["season", "team"]).size().unstack())


def build_retired() -> pd.DataFrame:
    """Players listed in the 'Retired players' tables (they leave the pool)."""
    rows = []
    for season in SEASONS:
        text = (WIKI_DIR / f"personnel_{season}.wiki").read_text(encoding="utf-8")
        for tbl in parse_tables(text):
            if "retire" not in tbl.caption.lower() and "retire" not in tbl.heading.lower():
                continue
            heads = [h.lower() for h in tbl.headers]
            if "name" not in heads and "player" not in heads:
                continue
            ni = heads.index("name") if "name" in heads else heads.index("player")
            for row in tbl.rows:
                if len(row) > ni and row[ni].text:
                    rows.append({"season": season, "player_name": row[ni].text.lstrip("| ").strip(),
                                 "wiki_title": row[ni].link})
    df = pd.DataFrame(rows).drop_duplicates("player_name")
    df.to_csv(AUCTION_RAW_DIR / "retired_players.csv", index=False)
    return df
