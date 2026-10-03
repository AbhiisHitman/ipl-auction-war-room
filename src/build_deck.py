"""Draft consulting deck (python-pptx), action titles on every slide.

    python -m src.build_deck              # CSK (illustrative client)
    python -m src.build_deck --team MI    # any franchise
    python -m src.build_deck --all        # all ten

Charts and tables are native PowerPoint objects (editable), built from
data/processed/ so the deck always matches the analysis.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

import numpy as np
import pandas as pd
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_AXIS_CROSSES, XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from .config import OUTPUTS_DIR, PROCESSED_DIR, assumptions, rules
from .economics import default_inputs, pnl
from .teams import active_codes, full_name

# ---------------------------------------------------------------- palette
NAVY = RGBColor(0x0E, 0x1B, 0x3D)      # dominant: night-match navy
INK = RGBColor(0x1F, 0x27, 0x37)
SLATE = RGBColor(0x5B, 0x67, 0x7D)
MUTED = RGBColor(0x8A, 0x93, 0xA6)
LINE = RGBColor(0xDD, 0xE1, 0xE8)
TINT = RGBColor(0xF3, 0xF5, 0xF9)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x1E, 0x8E, 0x4A)
AMBER = RGBColor(0xD9, 0x8E, 0x04)
RED = RGBColor(0xC8, 0x3A, 0x3A)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
GREY = RGBColor(0xB5, 0xB3, 0xAD)
STATUS = {"Green": GREEN, "Amber": AMBER, "Red": RED}

TEAM_ACCENT = {  # strong, print-safe accent per franchise (fills, badges)
    "CSK": "E0A800", "DC": "1F4FB4", "GT": "B08D45", "KKR": "5B3A8E", "LSG": "0091C8",
    "MI": "1660B8", "PBKS": "C8202D", "RR": "D0187A", "RCB": "C8161F", "SRH": "E35B12",
}
FONT = "Calibri"
W, H = Inches(13.333), Inches(7.5)
MX = Inches(0.6)  # side margin


def rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr)


def pct(x: float) -> str:
    """Percent with half-up rounding (0.525 -> 53%, matching the docs)."""
    return f"{int(x * 100 + 0.5)}%"


def cr(v: float | None, d: int = 1) -> str:
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"Rs {v:.{d}f} cr"


# ---------------------------------------------------------------- primitives
def text(slide, x, y, w, h, runs, size=14, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, name=None, spacing_after=0, italic=False):
    """Text box. `runs` = str, or list of paragraphs; a paragraph is a str or
    a list of (text, {bold,color,size,italic}) tuples."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(spacing_after)
        parts = para if isinstance(para, list) else [(para, {})]
        for t, o in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = o.get("color", color)
    return tb


def box(slide, x, y, w, h, fill=TINT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, name=None):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if name:
        s.name = name
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def badge(slide, x, y, label, fill, size=0.46, font_color=WHITE):
    """Motif: numbered circle (a cricket-ball badge)."""
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, Inches(size), Inches(size))
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.fill.background()
    c.shadow.inherit = False
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(label)
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(14), True, font_color
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return c


def table(slide, x, y, w, rows, col_w, header_fill=NAVY, size=11, row_h=0.36, fills=None, bold_cols=()):
    """Native table. rows[0] is the header. fills: {(r, c): RGBColor}."""
    nr, nc = len(rows), len(rows[0])
    gt = slide.shapes.add_table(nr, nc, x, y, w, Inches(row_h * nr)).table
    for j, cw in enumerate(col_w):
        gt.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        gt.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = gt.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = "" if val is None else str(val)
            r.font.name, r.font.size = FONT, Pt(size)
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = header_fill
                r.font.bold, r.font.color.rgb = True, WHITE
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else TINT
                r.font.color.rgb = INK
                r.font.bold = j in bold_cols
            if fills and (i, j) in fills:
                cell.fill.fore_color.rgb = fills[(i, j)]
                r.font.color.rgb, r.font.bold = WHITE, True
    return gt


# ---------------------------------------------------------------- layouts
class Deck:
    def __init__(self, team: str):
        self.team = team
        self.accent = rgb(TEAM_ACCENT[team])
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.blank = self.prs.slide_layouts[6]
        self.n = 0

    def content(self, title: str, source: str, kicker: str = "", notes: str = ""):
        """Light content slide: action title, kicker, footer with source + page."""
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = WHITE
        if kicker:
            text(s, MX, Inches(0.35), Inches(9), Inches(0.3), kicker.upper(), size=11, bold=True,
                 color=SLATE, name="Kicker")
        text(s, MX, Inches(0.62), W - 2 * MX, Inches(0.95), title, size=26, bold=True, color=NAVY,
             anchor=MSO_ANCHOR.TOP, name="Title")
        text(s, MX, H - Inches(0.48), Inches(10.5), Inches(0.3), f"Source: {source}", size=9, color=MUTED,
             name="Source")
        text(s, W - MX - Inches(2.6), H - Inches(0.48), Inches(2.6), Inches(0.3),
             [[(f"Auction War Room  |  {self.n}", {})]], size=9, color=MUTED, align=PP_ALIGN.RIGHT, name="Page")
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def dark(self, notes: str = ""):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = NAVY
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s


# ---------------------------------------------------------------- charts
def style_chart(chart, size=11):
    chart.font.name = FONT
    chart.font.size = Pt(size)
    chart.font.color.rgb = SLATE


def set_log_axis(axis) -> None:
    scaling = axis._element.find(qn("c:scaling"))
    lb = etree.SubElement(scaling, qn("c:logBase"))
    lb.set("val", "10")
    scaling.remove(lb)
    scaling.insert(0, lb)


def gridlines(axis, on=True):
    axis.has_major_gridlines = on
    if on:
        axis.major_gridlines.format.line.color.rgb = LINE
        axis.major_gridlines.format.line.width = Pt(0.75)
    axis.format.line.color.rgb = LINE


# ---------------------------------------------------------------- data
def load(team: str) -> dict:
    briefs = json.loads((PROCESSED_DIR / "team_briefs.json").read_text())
    players = pd.read_csv(PROCESSED_DIR / "players.csv")
    d = {
        "brief": briefs[team],
        "cov": pd.read_csv(PROCESSED_DIR / "coverage.csv").query("team == @team"),
        "cov_all": pd.read_csv(PROCESSED_DIR / "coverage.csv"),
        "recs": pd.read_csv(PROCESSED_DIR / "recommendations.csv").query("team == @team"),
        "summ": pd.read_csv(PROCESSED_DIR / "optimiser_summary.csv").query("team == @team").set_index("mode"),
        "scen": pd.read_csv(PROCESSED_DIR / "scenarios.csv").query("team == @team"),
        "table": pd.read_csv(PROCESSED_DIR / "league_table_2026.csv"),
        "players": players,
        "squad": players[players["current_team"].eq(team)],
        "market": json.loads((PROCESSED_DIR / "market_model.json").read_text()),
        "win": json.loads((PROCESSED_DIR / "win_model.json").read_text()),
        "train": pd.read_csv(PROCESSED_DIR / "market_training.csv"),
        "by_role": pd.read_csv(PROCESSED_DIR / "mispricing_by_role.csv"),
        "by_phase": pd.read_csv(PROCESSED_DIR / "mispricing_by_phase.csv"),
        "wv": pd.read_csv(PROCESSED_DIR / "wicket_values.csv").set_index("phase")["wicket_value_runs"],
        "homes": pd.read_csv(PROCESSED_DIR / "home_venues.csv").set_index("team")["venue"],
    }
    d["salary_cr"] = d["squad"]["current_salary_lakh"].sum() / 100
    inp = default_inputs(team, d["homes"][team], salary_cr=d["salary_cr"])
    d["pnl"] = {s: pnl(inp, s).set_index("line")["value_cr"] for s in ("missed_playoffs", "made_playoffs", "won_title")}
    return d


# ---------------------------------------------------------------- slides
def build(team: str = "CSK") -> str:
    d = load(team)
    deck = Deck(team)
    A = deck.accent
    b = d["brief"]
    name = full_name(team)
    mini = d["summ"].loc["mini_2027"]
    mega = d["summ"].loc["mega_2028"]
    recs = d["recs"][d["recs"]["mode"] == "mini_2027"]
    buys = recs[recs["action"].isin(["Buy", "Buy back"])]
    rel = recs[recs["action"] == "Release"]
    ret = recs[recs["action"] == "Retain"]
    freed = rel["player"].map(d["squad"].set_index("display_name")["current_salary_lakh"]).sum() / 100
    p0, p1 = mini["playoff_prob_before"], mini["playoff_prob_after"]
    mix = d["pnl"]["missed_playoffs"]["Central (fixed) share of revenue"]
    rev_gap = d["pnl"]["won_title"]["Total revenue"] - d["pnl"]["missed_playoffs"]["Total revenue"]
    red = b["red_roles"]
    amber = b["amber_roles"]
    gaps_txt = ", ".join([r.lower() for r in red + amber]) or "depth only"
    rho = d["win"]["realisation: realised = c + rho * planned_strength"]["rho"]
    r2s = d["win"]["structural: win_pct = a + b * realised_impact"]["r2"]
    finish = b["finish_2026"]
    src_core = "Cricsheet ball-by-ball 2008-2026; Wikipedia IPL auction tables 2022-26; team analysis"

    # 1 ---------------------------------------------------------------- title
    s = deck.dark(notes="Draft for discussion. The analysis covers all ten franchises; this deck uses "
                        f"{name} as the illustrative client.")
    tag = box(s, MX, Inches(1.25), Inches(1.1), Inches(0.5), fill=A, radius=0.5, name="Team tag")
    tf = tag.text_frame
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    r_ = tf.paragraphs[0].add_run()
    r_.text = team
    r_.font.name, r_.font.size, r_.font.bold = FONT, Pt(16), True
    r_.font.color.rgb = NAVY if team in ("CSK", "GT") else WHITE
    text(s, MX, Inches(2.0), Inches(11.5), Inches(2.0),
         [[(f"{name}: ", {"color": WHITE}),
           ("how to rebuild for the IPL 2027 auction and set up for the 2028 reset" if b["stance"] != "Win Now"
            else "how to win now at the IPL 2027 auction and set up for the 2028 reset", {"color": WHITE})]],
         size=40, bold=True)
    text(s, MX, Inches(4.25), Inches(10), Inches(0.9),
         "Squad strategy, purse allocation and bid ceilings, built from 295,732 deliveries and five years of auction prices",
         size=18, color=rgb("CADCFC"))
    text(s, MX, Inches(6.4), Inches(10), Inches(0.4),
         "Auction War Room  |  Draft for discussion  |  October 2026  |  Hypothetical engagement, not affiliated with the IPL or any franchise",
         size=11, color=rgb("8EA0C8"))

    # 2 ---------------------------------------------------------------- executive summary
    s = deck.content(
        f"Cut Rs {freed:.0f} cr of low-return contracts, fix {('the ' + red[0].lower() + ' gap') if red else 'the weakest roles'} with value buys, "
        f"and keep firepower for the 2028 mega-auction",
        src_core + "; franchise P&L model", kicker="Executive summary",
        notes="Answer first. Three messages, then the numbers that back them.")
    msgs = [
        ("Release what the output does not justify",
         f"{len(rel)} releases free Rs {freed:.0f} cr. The biggest contracts in the squad deliver below-average "
         f"impact; the purse goes further on output the market underprices."),
        ("Buy for the gaps, not the names",
         (f"Red: {', '.join(r.lower() for r in red)}" if red else "No Red roles")
         + f"; Amber: {', '.join(a.lower() for a in amber) or 'none'}. "
         f"{len(buys)} targets, each with a bid ceiling and a cheaper backup in the same role."),
        ("2027 is a bridge year",
         "It is the last season of the 2025-27 cycle. One-year value veterans now; the real rebuild happens "
         "in the 2028 mega-auction, when every franchise resets its purse."),
    ]
    y = Inches(1.85)
    for i, (h, body) in enumerate(msgs):
        badge(s, MX, y, i + 1, A, font_color=NAVY if team in ("CSK", "GT") else WHITE)
        text(s, MX + Inches(0.7), y - Inches(0.02), Inches(7.2), Inches(0.4), h, size=17, bold=True, color=NAVY)
        text(s, MX + Inches(0.7), y + Inches(0.4), Inches(7.2), Inches(0.9), body, size=13, color=SLATE)
        y += Inches(1.5)
    stats = [(f"{pct(p0)} to {pct(p1)}", "playoff chance, current squad vs plan"),
             (f"Rs {mini['purse_used_cr']:.0f} cr", f"purse used of Rs {mini['purse_total_cr']:.0f} cr"),
             (f"+Rs {mini['exp_profit_after_cr'] - mini['exp_profit_before_cr']:.0f} cr", "expected operating profit, mostly lower wages"),
             (f"{pct(mix)}", "of revenue is fixed central income")]
    box(s, Inches(8.55), Inches(1.75), Inches(4.18), Inches(4.9), fill=TINT, name="Stat panel")
    for i, (v, lab) in enumerate(stats):
        yy = Inches(1.95) + Inches(1.18) * i
        text(s, Inches(8.85), yy, Inches(3.7), Inches(0.6), v, size=28, bold=True, color=NAVY)
        text(s, Inches(8.85), yy + Inches(0.58), Inches(3.7), Inches(0.4), lab, size=12, color=SLATE)

    # 3 ---------------------------------------------------------------- situation
    s = deck.content(
        f"{name} finished {finish}th in 2026 with Rs {b['purse_left_cr']:.1f} cr left and no overseas slots: "
        f"any upgrade has to be funded by releases",
        "Cricsheet 2026 league table; 2026 retention and auction records (Wikipedia)", kicker="Situation and key question",
        notes="The constraint is money and slots, not ambition. That is why the release decisions come first.")
    tab = d["table"]
    rows = [["#", "Team", "W", "Pts"]] + [[int(r.position), r.team, int(r.wins), int(r.points)] for r in tab.itertuples()]
    fills = {}
    for i, r in enumerate(tab.itertuples(), start=1):
        if r.team == team:
            for j in range(4):
                fills[(i, j)] = A
    table(s, MX, Inches(1.85), Inches(3.3), rows, [0.45, 1.25, 0.7, 0.9], size=11, row_h=0.4, fills=fills)
    text(s, MX, Inches(6.35), Inches(3.4), Inches(0.4), "2026 league stage (net run rate not shown)", size=10, color=MUTED)
    text(s, Inches(4.4), Inches(1.85), Inches(8.3), Inches(0.5), "Key question", size=13, bold=True, color=SLATE)
    text(s, Inches(4.4), Inches(2.2), Inches(8.3), Inches(1.0),
         f"How should {name} rebuild its squad and allocate its purse for the IPL 2027 auction to maximise wins and commercial value?",
         size=18, bold=True, color=NAVY)
    tree = ["How does the franchise make money?", "What actually wins IPL matches?", "Where does the auction misprice players?",
            "Where is our squad weak?", "What is the best squad we can afford?", "What exactly should we do?", "What is it worth?"]
    for i, q in enumerate(tree):
        col, row = divmod(i, 4)
        x = Inches(4.4) + Inches(4.2) * col
        yy = Inches(3.45) + Inches(0.72) * row
        badge(s, x, yy, i + 1, NAVY, size=0.42)
        text(s, x + Inches(0.55), yy + Inches(0.06), Inches(3.55), Inches(0.4), q, size=13, color=INK)

    # 4 ---------------------------------------------------------------- money
    s = deck.content(
        f"{pct(mix)} of revenue is fixed central income: a title adds only Rs {rev_gap:.0f} cr, so cost discipline matters as much as winning",
        "Media rights Rs 48,390 cr 2023-27; Tata title sponsorship; Houlihan Lokey 2025 brand values; BCCI 2026 prize money; team assumptions (see Excel model)",
        kicker="How the franchise makes money",
        notes="All inputs live in outputs/excel/franchise_model.xlsx with formulas; assumptions are flagged.")
    groups = {"Central media rights": ["Central media rights share"], "Central sponsorship": ["Central sponsorship share"],
              "Team sponsorship, tickets, merchandise": ["Team sponsorships", "Ticketing (home matches)", "Merchandise"],
              "Prize money": ["Prize money"]}
    labels = {"missed_playoffs": "Missed playoffs", "made_playoffs": "Made playoffs", "won_title": "Won title"}
    cd = CategoryChartData()
    cd.categories = list(labels.values())
    for g, lines in groups.items():
        cd.add_series(g, [round(float(d["pnl"][k][lines].sum()), 1) for k in labels])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, MX, Inches(1.8), Inches(8.2), Inches(4.6), cd)
    ch = gf.chart
    style_chart(ch)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.legend.font.size = Pt(11)
    for ser, col in zip(ch.series, [BLUE, rgb("EB6834"), rgb("1BAF7A"), rgb("EDA100")]):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = col
    ch.plots[0].gap_width = 60
    pl = ch.plots[0]
    pl.has_data_labels = True
    pl.data_labels.position = XL_LABEL_POSITION.CENTER
    pl.data_labels.number_format = '0;;;'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.font.size = Pt(10)
    pl.data_labels.font.color.rgb = WHITE
    gridlines(ch.value_axis)
    ch.value_axis.has_title = False
    gridlines(ch.category_axis, on=False)
    box(s, Inches(9.1), Inches(1.85), Inches(3.63), Inches(4.5), fill=TINT, name="Callouts")
    pnl_m = d["pnl"]["missed_playoffs"]
    callouts = [(cr(pnl_m["Total revenue"], 0), "revenue if the team misses the playoffs"),
                (f"+Rs {rev_gap:.0f} cr", "extra revenue from winning the title"),
                (cr(pnl_m["Operating profit"], 0), "operating profit (before any franchise fee)")]
    for i, (v, lab) in enumerate(callouts):
        yy = Inches(2.05) + Inches(1.42) * i
        text(s, Inches(9.35), yy, Inches(3.2), Inches(0.55), v, size=26, bold=True, color=NAVY)
        text(s, Inches(9.35), yy + Inches(0.55), Inches(3.2), Inches(0.6), lab, size=12, color=SLATE)

    # 5 ---------------------------------------------------------------- what wins
    s = deck.content(
        f"Runs added versus an average player explain {pct(r2s)} of win %; early wickets are worth 7x late ones",
        "Cricsheet ball-by-ball 2008-2026; run-expectancy model on 2023-26 first innings; 132 team-seasons", kicker="What wins IPL matches",
        notes="Impact Score = runs a player adds per match vs a league-average player in the same phase and season, "
              "with wickets valued from a run-expectancy table and small samples shrunk toward average.")
    wv = d["wv"]
    for i, (ph, lab) in enumerate([("Powerplay", "Powerplay (overs 1-6)"), ("Middle", "Middle (7-15)"), ("Death", "Death (16-20)")]):
        x = MX + Inches(1.38) * i
        box(s, x, Inches(1.85), Inches(1.25), Inches(1.5), fill=TINT)
        text(s, x, Inches(2.0), Inches(1.25), Inches(0.6), f"{wv[ph]:.1f}", size=30, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
        text(s, x + Inches(0.08), Inches(2.62), Inches(1.09), Inches(0.6), f"runs per wicket\n{lab}", size=10, color=SLATE, align=PP_ALIGN.CENTER)
    text(s, MX, Inches(3.6), Inches(4.0), Inches(2.7), [
        [("Impact Score, in one sentence: ", {"bold": True, "color": NAVY}),
         ("the runs a player adds per match compared with a league-average player in the same phase and season.", {})],
        [("Validated: ", {"bold": True, "color": NAVY}),
         (f"a team's same-season total impact explains {pct(r2s)} of the variation in win % (+10 runs/match = about +7 points of win %).", {})],
        [("Caveat: ", {"bold": True, "color": NAVY}),
         (f"only {pct(rho)} of a planned strength gain shows up the next season.", {})],
    ], size=13, color=SLATE, spacing_after=10)
    top = d["players"][d["players"]["has_impact"]].nlargest(12, "impact").iloc[::-1]
    cd = CategoryChartData()
    cd.categories = [f"{n} ({t})" if isinstance(t, str) else n for n, t in zip(top["display_name"], top["current_team"])]
    cd.add_series("Impact Score", [round(float(v), 1) for v in top["impact"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(4.9), Inches(1.75), Inches(7.83), Inches(4.75), cd)
    ch = gf.chart
    style_chart(ch, 11)
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "Top 12 players by Impact Score going into 2027 (runs/match)"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = INK
    ser = ch.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = BLUE
    ch.plots[0].gap_width = 45
    ch.plots[0].has_data_labels = True
    ch.plots[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ch.plots[0].data_labels.number_format = '0.0'
    ch.plots[0].data_labels.number_format_is_linked = False
    ch.plots[0].data_labels.font.size = Pt(10)
    gridlines(ch.value_axis, on=False)
    ch.value_axis.visible = False
    gridlines(ch.category_axis, on=False)

    # 6 ---------------------------------------------------------------- market
    ins = d["market"]["insights"]
    s = deck.content(
        "The auction pays for reputation: a cap adds 157% to price, output only 24% per run, so specialists are mispriced",
        "284 players sold at the 2022-26 auctions with an Impact Score; log-price regression (R² 0.30)", kicker="Where the market misprices players",
        notes="Fair value = typical price for the same impact, cap status and auction year. Mispricing = (fair - paid) / paid.")
    t = d["train"].copy()
    t["price"] = t["sold_price_lakh"] / 100
    bands = [("Near fair value", GREY, (t["mispricing_pct"] <= 1) & (t["mispricing_pct"] >= -0.5)),
             ("Overpriced (paid > 2x fair)", RED, t["mispricing_pct"] < -0.5),
             ("Underpriced (paid < 50% of fair)", BLUE, t["mispricing_pct"] > 1)]
    cd = XyChartData()
    for lab, _, m in bands:
        ser = cd.add_series(f"{lab} (n={int(m.sum())})")
        for x, y in zip(t.loc[m, "impact"], t.loc[m, "price"]):
            ser.add_data_point(round(float(x), 2), round(float(y), 2))
    gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, MX, Inches(1.75), Inches(7.6), Inches(4.8), cd)
    ch = gf.chart
    style_chart(ch, 10)
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    for ser, (_, col, _) in zip(ch.series, bands):
        ser.marker.style = XL_MARKER_STYLE.CIRCLE
        ser.marker.size = 7
        ser.marker.format.fill.solid()
        ser.marker.format.fill.fore_color.rgb = col
        ser.marker.format.line.color.rgb = WHITE
        ser.format.line.fill.background()
    va = ch.value_axis
    set_log_axis(va)
    va.minimum_scale, va.maximum_scale = 0.1, 40
    va.crosses = XL_AXIS_CROSSES.MINIMUM  # x axis sits at the bottom
    va.has_title = True
    va.axis_title.text_frame.text = "Price paid, Rs crore (log scale)"
    va.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
    gridlines(va)
    ca = ch.category_axis
    ca.has_title = True
    ca.axis_title.text_frame.text = "Impact Score at auction (runs/match vs average)"
    ca.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
    gridlines(ca, on=False)
    ca.minimum_scale, ca.maximum_scale = -7, 9
    ca.crosses = XL_AXIS_CROSSES.MINIMUM  # y axis sits at the left edge
    y = Inches(1.8)
    for i, msg in enumerate(ins):
        badge(s, Inches(8.5), y, i + 1, A, size=0.42, font_color=NAVY if team in ("CSK", "GT") else WHITE)
        text(s, Inches(9.05), y - Inches(0.02), Inches(3.68), Inches(1.5), msg, size=12.5, color=INK)
        y += Inches(1.6)

    # 7 ---------------------------------------------------------------- gaps
    cov = d["cov"].set_index("role")
    s = deck.content(
        f"{name} has {len(red)} Red and {len(amber)} Amber roles: {gaps_txt} are where the purse should go",
        "Role coverage of the 2026 squad vs league benchmarks (Impact Score, 2024-26 weighted)", kicker="Our squad gaps",
        notes="Green: our k-th best player in the role ranks in the league's top 10k (starter quality for ten teams). "
              "Amber: top 15k. Red: below that, or too few players.")
    rows = [["Role", "Need", "Status", "Our k-th best vs league", "Players in squad"]]
    fills = {}
    for i, (role, r) in enumerate(cov.iterrows(), start=1):
        players_short = ", ".join(str(r["squad_players"]).split(", ")[:3]) if isinstance(r["squad_players"], str) else "None"
        rows.append([role, int(r["needed"]), r["status"], r["explanation"].replace("(starter level = ", "(starter = "), players_short])
        fills[(i, 2)] = STATUS[r["status"]]
    table(s, MX, Inches(1.75), Inches(12.1), rows, [1.75, 0.65, 0.9, 5.4, 3.4], size=11, row_h=0.42, fills=fills)
    text(s, MX, Inches(6.5), Inches(12), Inches(0.35),
         "Status cells are coloured and labelled. Venue: " + b["home_venue"] + " adjusts spin, pace and death weights in the optimiser.",
         size=10, color=MUTED)

    # 8 ---------------------------------------------------------------- strategy
    s = deck.content(
        f"Strategy: {b['stance']}, with three moves for 2027 and the big rebuild held back for 2028",
        "Team strategy model: role gaps, home-ground profile, 2026 finish and squad age", kicker="Recommended auction strategy",
        notes=b["stance_reason"])
    cards = [
        ("Free the purse", f"Release {len(rel)} players (Rs {freed:.0f} cr) whose salary sits well above what their output justifies.",
         f"Wage bill falls from {cr(d['salary_cr'], 0)} to {cr(mini['purse_used_cr'], 0)}"),
        ("Fix the gaps", "Spend first on " + (", ".join(r.lower() for r in red + amber) or "depth") +
         "; every target has a walk-away ceiling and a backup.", f"{len(buys)} targets, {int(buys['starter'].sum())} of them starters"),
        ("Bridge to 2028", "Prefer one-year value veterans over long, expensive bets: the 2028 mega-auction resets every squad.",
         f"Mega-auction plan lifts playoff odds to {pct(mega['playoff_prob_after'])}"),
    ]
    for i, (h, body, kpi) in enumerate(cards):
        x = MX + Inches(4.1) * i
        box(s, x, Inches(1.85), Inches(3.85), Inches(3.55), fill=TINT, name=f"Card {i + 1}")
        badge(s, x + Inches(0.3), Inches(2.1), i + 1, A, font_color=NAVY if team in ("CSK", "GT") else WHITE)
        text(s, x + Inches(0.3), Inches(2.75), Inches(3.3), Inches(0.5), h, size=19, bold=True, color=NAVY)
        text(s, x + Inches(0.3), Inches(3.3), Inches(3.3), Inches(1.7), body, size=14, color=SLATE)
        text(s, x + Inches(0.3), Inches(4.5), Inches(3.3), Inches(0.7), kpi, size=13, bold=True, color=INK)
    text(s, MX, Inches(5.75), Inches(12.1), Inches(0.8), [
        [("Why this stance: ", {"bold": True, "color": NAVY}), (b["stance_reason"] + " ", {}),
         ("Home ground: ", {"bold": True, "color": NAVY}), (b["home_venue"] + "; its spin, pace and death-over profile adjusts the role weights.", {})]],
        size=13, color=SLATE)

    # 9 ---------------------------------------------------------------- player recommendations
    lead = buys[buys["gap_filled"].isin(["Red", "Amber"])].head(2)
    lead_txt = " and ".join(f"{r.player} ({r.role.lower()})" for r in lead.itertuples()) if len(lead) else ", ".join(buys.head(2)["player"])
    s = deck.content(
        f"Buy {len(buys)} targets, led by {lead_txt} for the gaps; retain {len(ret)}, release {len(rel)}",
        "Optimiser (PuLP) on 2027 mini-auction pool; fair value and likely price from market models", kicker="Player recommendations",
        notes="Full table with rationale, risk and backup for every player: data/processed/recommendations.csv and the web app.")
    top_buys = buys.head(8)
    rows = [["Buy target", "Role", "Impact", "Fair value", "Ceiling", "Likely price", "Backup option"]]
    for r in top_buys.itertuples():
        rows.append([r.player, r.role if isinstance(r.role, str) else "Utility", f"{r.impact_score:+.1f}",
                     cr(r.fair_value_cr), cr(r.bid_ceiling_cr), cr(r.expected_cost_cr),
                     str(r.backup_option).split(" (")[0] if isinstance(r.backup_option, str) else ""])
    table(s, MX, Inches(1.75), Inches(8.45), rows, [1.85, 1.35, 0.7, 1.05, 1.0, 1.1, 1.4], size=10.5, row_h=0.42, bold_cols=(0,))
    box(s, Inches(9.3), Inches(1.75), Inches(3.43), Inches(4.75), fill=TINT, name="Squad decisions")
    text(s, Inches(9.55), Inches(1.95), Inches(3.0), Inches(0.4), "Release (largest salaries)", size=13, bold=True, color=NAVY)
    rel_sal = rel.assign(sal=rel["player"].map(d["squad"].set_index("display_name")["current_salary_lakh"])).sort_values("sal", ascending=False)
    text(s, Inches(9.55), Inches(2.35), Inches(3.0), Inches(1.9),
         [f"{r.player}  ({cr(r.sal / 100)})" for r in rel_sal.head(5).itertuples()], size=12, color=SLATE, spacing_after=3)
    text(s, Inches(9.55), Inches(4.25), Inches(3.0), Inches(0.4), "Retain (highest impact)", size=13, bold=True, color=NAVY)
    text(s, Inches(9.55), Inches(4.65), Inches(3.0), Inches(1.7),
         [f"{r.player}  ({r.impact_score:+.1f})" for r in ret.sort_values("impact_score", ascending=False).head(5).itertuples()],
         size=12, color=SLATE, spacing_after=3)
    text(s, MX, Inches(5.65), Inches(8.4), Inches(0.8),
         "Ceiling = fair value + premium for gap-filling roles (+15% Red, +5% Amber). Where the likely price is above the ceiling, "
         "bid only to the ceiling and move to the backup.", size=11, color=MUTED)

    # 10 ---------------------------------------------------------------- scenarios & ceilings
    sc = d["scen"][d["scen"]["mode"] == "mini_2027"]
    s = deck.content(
        f"The plan is robust: at +30% rival bidding the squad strength holds at {sc['strength_after'].min():.1f} and playoff odds stay near {pct(sc['playoff_prob_after'].min())}",
        "Optimiser re-run under Win Now / Long-Term weights and +10/20/30% rival price inflation", kicker="Scenarios and bid ceilings",
        notes="Where likely price exceeds our ceiling, the plan substitutes the backup rather than overpay.")
    rows = [["Scenario", "Purse used", "Buys", "Strength", "Playoff chance"]]
    for r in sc.itertuples():
        rows.append([r.scenario, cr(r.purse_used_cr), int(r.buys), f"{r.strength_after:.1f}", pct(r.playoff_prob_after)])
    table(s, MX, Inches(1.8), Inches(5.6), rows, [1.9, 1.15, 0.65, 0.9, 1.0], size=11, row_h=0.45)
    cb = buys.dropna(subset=["bid_ceiling_cr"]).head(7).iloc[::-1]
    cd = CategoryChartData()
    cd.categories = list(cb["player"])
    cd.add_series("Bid ceiling", [round(float(v), 2) for v in cb["bid_ceiling_cr"]])
    cd.add_series("Likely price", [round(float(v), 2) for v in cb["expected_cost_cr"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(6.6), Inches(1.75), Inches(6.13), Inches(4.75), cd)
    ch = gf.chart
    style_chart(ch, 10)
    ch.has_title = True
    ch.chart_title.text_frame.text = "Bid ceiling vs likely price, Rs crore"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = INK
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    for ser, col in zip(ch.series, [NAVY, rgb("EB6834")]):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = col
    ch.plots[0].gap_width = 60
    ch.plots[0].overlap = -10
    ch.plots[0].has_data_labels = True
    ch.plots[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ch.plots[0].data_labels.number_format = '0.0'
    ch.plots[0].data_labels.number_format_is_linked = False
    ch.plots[0].data_labels.font.size = Pt(9)
    ch.value_axis.visible = False
    gridlines(ch.value_axis, on=False)
    gridlines(ch.category_axis, on=False)

    # 11 ---------------------------------------------------------------- impact chain
    gain = mini["exp_profit_after_cr"] - mini["exp_profit_before_cr"]
    rev_gain = mini["exp_revenue_after_cr"] - mini["exp_revenue_before_cr"]
    s = deck.content(
        f"Expected impact: playoff odds {pct(p0)} to {pct(p1)} and +Rs {gain:.0f} cr expected profit, most of it from a leaner wage bill",
        "Impact model: realised-strength regression (132 team-seasons), binomial over 14 games, probability-weighted P&L",
        kicker="Expected impact on wins and revenue",
        notes=f"Only {pct(rho)} of a planned strength gain is realised on average; treat squad gains as directional.")
    chain = [("Squad strength", f"{mini['strength_before']:.1f} to {mini['strength_after']:.1f}", "best-12 Impact, runs/match"),
             ("Win %", f"{mini['win_pct_before']:.1%} to {mini['win_pct_after']:.1%}", f"only {pct(rho)} of planned gain realised"),
             ("Playoff chance", f"{pct(p0)} to {pct(p1)}", "8 wins usually qualify"),
             ("Expected revenue", f"+Rs {rev_gain:.1f} cr", f"{pct(mix)} of revenue is fixed"),
             ("Expected op. profit", f"+Rs {gain:.0f} cr", "lower wages + small revenue gain")]
    bw = Inches(2.22)
    for i, (h, v, sub) in enumerate(chain):
        x = MX + (bw + Inches(0.25)) * i
        box(s, x, Inches(2.2), bw, Inches(2.3), fill=NAVY if i == len(chain) - 1 else TINT, name=f"Chain {i + 1}")
        fg = WHITE if i == len(chain) - 1 else NAVY
        text(s, x + Inches(0.18), Inches(2.4), bw - Inches(0.36), Inches(0.4), h, size=13, bold=True,
             color=rgb("CADCFC") if i == len(chain) - 1 else SLATE)
        text(s, x + Inches(0.18), Inches(2.85), bw - Inches(0.36), Inches(0.9), v, size=21, bold=True, color=fg)
        text(s, x + Inches(0.18), Inches(3.75), bw - Inches(0.36), Inches(0.6), sub, size=11,
             color=rgb("CADCFC") if i == len(chain) - 1 else SLATE)
        if i < len(chain) - 1:
            arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + bw + Inches(0.03), Inches(3.2), Inches(0.19), Inches(0.3))
            arr.fill.solid()
            arr.fill.fore_color.rgb = MUTED
            arr.line.fill.background()
    text(s, MX, Inches(4.95), Inches(12.1), Inches(1.3), [
        [("Mega-auction 2028: ", {"bold": True, "color": NAVY}),
         (f"with the whole league back in the pool, the same method lifts playoff odds to {pct(mega['playoff_prob_after'])} "
          f"(strength {mega['strength_before']:.1f} to {mega['strength_after']:.1f}).", {})],
        [("Read with care: ", {"bold": True, "color": NAVY}),
         ("the profit gain is mostly salary saved; revenue barely moves because central income dominates.", {})],
    ], size=13, color=SLATE, spacing_after=8)

    # 12 ---------------------------------------------------------------- risks
    s = deck.content(
        "Five risks to manage: model blind spots on leadership and youth matter most",
        "Team analysis; model limitations in docs/methodology.md", kicker="Risks and mitigations",
        notes="Model outputs are inputs to judgement, not a replacement for it.")
    big_rel = rel_sal.head(1)["player"].tolist()
    ages = rel["player"].map(d["squad"].set_index("display_name")["age_at_auction"])
    young = rel[ages <= 23]["player"].tolist()
    risks = [
        ("Leadership and brand value are not in the model",
         f"Review high-profile releases (e.g. {', '.join(big_rel)}) with the board; keep the captain even at a premium."),
        ("Young players look weak on small samples",
         (f"{' and '.join(young[:2])} ({'both ' if len(young) > 1 else ''}23 or under) rate low on few balls: keep one as a development bet."
          if young else "Shrinkage under-rates breakouts: keep one high-upside youngster as a development bet.")),
        ("Bidding wars push prices past our ceilings",
         "Hard walk-away ceilings; pre-agreed backups in the same role; plan tested at +30% inflation."),
        ("Projected releases may not happen",
         "Several targets depend on rivals releasing them on 15 Nov; re-run the optimiser on the real lists."),
        ("Veterans and overseas availability",
         "Age 35+ and international clashes: favour one-year deals and carry a like-for-like Indian backup."),
    ]
    rows = [["Risk", "Mitigation"]] + [[r, m] for r, m in risks]
    table(s, MX, Inches(1.8), Inches(12.1), rows, [4.6, 7.5], size=13, row_h=0.78, bold_cols=(0,))

    # 13 ---------------------------------------------------------------- next steps
    s = deck.content(
        "Next steps: lock retentions by 15 November, then rehearse the auction against live rival lists",
        "IPL calendar (retention deadline mid-November; auction second week of December 2026, per Business Standard)",
        kicker="Next steps", notes="Each step re-runs the same pipeline: python -m src.pipeline, then the app updates.")
    steps = [("Now - 10 Nov", "Board review of releases", "Leadership and youth exceptions; confirm captain"),
             ("15 Nov", "Submit retention list", "Then load every team's real releases and re-run"),
             ("16 Nov - 5 Dec", "Auction rehearsal", "Live simulator, ceilings, backups, rival purses"),
             ("Dec 2026", "Auction day", "Bid to ceilings; switch to backups in real time"),
             ("2027 season", "Track and prepare 2028", "Monitor impact; plan the mega-auction retentions")]
    for i, (when, what, how) in enumerate(steps):
        x = MX + Inches(2.47) * i
        badge(s, x, Inches(2.6), i + 1, A, size=0.5, font_color=NAVY if team in ("CSK", "GT") else WHITE)
        if i < len(steps) - 1:
            ln = s.shapes.add_connector(1, x + Inches(0.55), Inches(2.85), x + Inches(2.42), Inches(2.85))
            ln.line.color.rgb = LINE
            ln.line.width = Pt(2)
        text(s, x, Inches(3.35), Inches(2.25), Inches(0.35), when, size=12, bold=True, color=SLATE)
        text(s, x, Inches(3.75), Inches(2.25), Inches(0.7), what, size=17, bold=True, color=NAVY)
        text(s, x, Inches(4.5), Inches(2.25), Inches(1.2), how, size=13, color=SLATE)

    # 14 ---------------------------------------------------------------- appendix
    s = deck.content(
        "Appendix: every method is simple enough to explain in one sentence, and every assumption is flagged",
        "docs/methodology.md, docs/sources.md, config/assumptions.yaml, config/rules.yaml", kicker="Appendix: methodology and assumptions")
    R = rules()
    rows = [["Component", "Method in one sentence", "Main limitation"],
            ["Impact Score", "Runs added per match vs an average player in the same phase/season; wickets valued by run expectancy; small samples shrunk", "Ignores fielding, captaincy, opposition"],
            ["Fair value", "Typical price for the same output, cap status and year (log-price regression, R² 0.30)", "Bidding dynamics; unsold players missing"],
            ["Likely price", "Fair-value model plus previous contract as a reputation proxy (R² 0.38)", "Reputation proxy is crude"],
            ["Role gaps", "League rank of the squad's k-th best player per data-driven role (Green / Amber / Red)", "Thresholds are judgement calls"],
            ["Optimiser", "Integer program: best-12 value within purse, squad, overseas and role rules", "Rivals do not react"],
            ["Impact chain", "Strength to win % (R² 0.53), realisation factor, binomial playoff odds, weighted P&L", "Next-season forecasts are noisy"],
            ["Key assumptions", f"2027 purse Rs {R['modes']['mini_2027']['purse_lakh']['value'] / 100:.0f} cr (unannounced); 2028 rules = 2025 framework; 50% central-revenue share", "Update when BCCI announces"]]
    table(s, MX, Inches(1.75), Inches(12.1), rows, [1.8, 6.8, 3.5], size=11, row_h=0.56, bold_cols=(0,))

    out = OUTPUTS_DIR / "deck" / f"auction_war_room_{team}.pptx"
    out.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(out)
    return str(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="CSK")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    for t in (active_codes() if a.all else [a.team.upper()]):
        print(build(t))
