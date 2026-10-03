# Sources

Every external figure, where it came from, and when it was checked. All checked **2026-10-03** unless stated.
Items not listed here are assumptions, and each one carries its reason in `config/assumptions.yaml` or `config/rules.yaml`.

## Match data
| Data | Source | Notes |
|---|---|---|
| Ball-by-ball, 1,243 IPL matches 2008-2026 | Cricsheet, `ipl_male_csv2.zip` - https://cricsheet.org/downloads/ | Downloaded 2026-10-03; last match 31 May 2026 (IPL 2026 final). |
| Player register | https://cricsheet.org/register/people.csv, names.csv | Identifiers only. |

## Auction and contract data
| Data | Source | Notes |
|---|---|---|
| Sold + retained players, prices, 2022-2026 | Wikipedia "List of {2022..2026} Indian Premier League personnel changes" (raw wikitext in `data/raw/auction/wiki/`) | The tables cite ESPNcricinfo and IPLT20.com. 2026 parse = 173 retained + 77 sold (matches the page summary). 2025 tables list 180 sold vs 182 in the page summary (2 rows missing on Wikipedia). |
| Nationality gaps (4 players) | `data/raw/auction/nationality_overrides.csv` | Filled manually where the Wikipedia row had no flag. |
| Retired players | Same Wikipedia pages ("Retired players" tables) | Removed from the auction pool. |
| Player bios (birth date, bowling style, role, caps) | Wikipedia infoboxes via the MediaWiki API (cache in `data/raw/players/`) | 93.6% of players found. |

## Rules (`config/rules.yaml`)
| Rule | Source |
|---|---|
| Squad 18-25, max 8 overseas, max 4 overseas in XI, Impact Player | https://en.wikipedia.org/wiki/Indian_Premier_League (Player acquisition, Rules) |
| 2026 purse Rs 125 cr, 75% minimum spend | Wikipedia 2026 personnel page; https://www.espncricinfo.com/story/ipl-auction-2026-faqs-when-where-who-and-how-much-1515453 |
| Overseas fee cap Rs 18 cr | Indian Express (cited on Wikipedia 2026 page) |
| Match fee Rs 7.5 lakh | Times of India, 29 Sep 2024 (cited on Wikipedia 2025 page) |
| 2025 retention: 6 incl. RTM, max 5 capped / 2 uncapped, Rs 120 cr purse | Wikipedia 2025 personnel page (Retention policy) |
| 2027 auction: India, second week of Dec 2026 | Business Standard, 19 Sep 2026 |
| **Not yet announced:** 2027 purse, all 2028 mega-auction rules | Marked as assumptions |

## Economics (`config/assumptions.yaml`)
| Figure | Value | Source |
|---|---|---|
| Media rights 2023-27 | Rs 48,390 cr | https://scroll.in/field/1025995/ipl-media-rights-for-2023-27-sold-for-rs-48390-crore-star-india-win-tv-deal-viacom18-bag-digital |
| Title sponsorship (Tata) 2024-28 | Rs 500 cr / season | Wikipedia IPL article, citing Times of India (19 Jan 2024) |
| Prize money 2026 | Winner 20, runner-up 12.5, 3rd 7, 4th 6.5 (Rs cr) | https://www.business-standard.com/cricket/ipl/ipl-2026-prize-money-how-much-money-does-the-winner-and-runner-up-win-126053100371_1.html (some outlets report Rs 13 cr for runner-up) |
| Brand values 2025 (USD m) | RCB 269, MI 242, CSK 235, KKR 227, SRH 154, DC 152, RR 146, GT 142, PBKS 141, LSG 122 | Houlihan Lokey, *IPL Valuation Study 2025* - http://cdn.hl.com/pdf/2025/ipl-study-2025.pdf (local copy `data/raw/hl_ipl_study_2025.pdf`) |
| Top-franchise revenue Rs 650-700 cr, up to 80% visible pre-season | | Same Houlihan Lokey study (calibration target) |
| LSG / GT franchise bids | Rs 7,000 cr / Rs 5,200 cr (2021) | Wikipedia IPL article, citing Cricbuzz (25 Oct 2021) |
| Stadium capacities | see assumptions.yaml | Wikipedia stadium infoboxes (most cite bcci.tv/venues) |
| Franchise share of central revenue (45-50%) | | Secondary sources, e.g. https://www.dezerv.in/newsletter/ipl-business-model-that-hit-sixer/ (treated as an assumption) |
