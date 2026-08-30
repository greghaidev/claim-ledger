> A real ledger, produced by the command in `README.md` on 2026-08-30 with
> `--reviewers minimax/minimax-m3`. Committed so you can see the output shape without
> spending anything. Your own run will differ in wording — reviewers are not deterministic —
> but the classifications on this example have been stable across seats.

# Fact-Check Gate ledger — verdict: **FAIL**

- Artifact: `example/report.md`
- Class: light  ·  Aggregation: OR-of-FAILs (unchaired; any reviewer FAIL fails the artifact)
- Cost: $0.0037

## minimax/minimax-m3 — **FAIL**
_QoQ growth claim of 18% is CONTRADICTED by data (actual 5.82%); guidance, customer satisfaction, and market share claims are UNTRACEABLE_

| Claim | Class | Cited source | Note |
|---|---|---|---|
| Second-half revenue across the four sales regions totaled $2,546,000 | TRACEABLE | example/derive.py: total = q3 + q4; sales.csv rows 1-8 | 1,237,000 + 1,309,000 = 2,546,000 |
| Q3 revenue was $1,237,000 | TRACEABLE | example/derive.py: by_quarter['2025-Q3']; sales.csv Q3 rows | 412600+271400+214300+338700 = 1,237,000 |
| Q4 revenue was $1,309,000 | TRACEABLE | example/derive.py: by_quarter['2025-Q4']; sales.csv Q4 rows | 477900+289100+229800+312200 = 1,309,000 |
| North is the strongest region, closing the half at $890,500 | TRACEABLE | example/derive.py: by_region['North']; sales.csv North rows | 412600+477900 = 890,500; max of by_region |
| North is more than any other region | TRACEABLE | example/derive.py: top_region; sales.csv | North 890,500 > West 650,900 > South 560,500 > East 444,100 |
| North is roughly a third of total revenue | TRACEABLE | example/derive.py + sales.csv | 890,500 / 2,546,000 = 34.97%, reasonably 'roughly a third' |
| North grew fastest in absolute terms, adding $65,300 between quarters | TRACEABLE | example/derive.py; sales.csv North rows | 477,900 - 412,600 = 65,300; exceeds South +17,700, East +15,500, West -26,500 |
| Quarter-over-quarter revenue growth came in at 18% | CONTRADICTED | example/derive.py: growth = (q4-q3)/q3*100 | Actual growth is (1,309,000-1,237,000)/1,237,000 = 5.82%, not 18% |
| Comfortably ahead of the 12% we guided to at the start of the half | UNTRACEABLE | none | No guidance figure exists in primary data or lineage |
| West was the only region to decline | TRACEABLE | example/derive.py: declines list; sales.csv | Only West has Q4 < Q3 revenue |
| West fell from $338,700 in Q3 to $312,200 in Q4 | TRACEABLE | sales.csv West rows | Direct match to primary data |
| West moved 114 fewer units quarter over quarter | TRACEABLE | sales.csv West rows | 1512 - 1398 = 114 |
| West's average selling price held steady | TRACEABLE | sales.csv West rows | ASP Q3 = 338700/1512 = $224.01; ASP Q4 = 312200/1398 = $223.32; ~0.3% change, reasonably 'steady' |
| Customer satisfaction improved across all four regions during the half | UNTRACEABLE | none | No customer satisfaction data in primary data or lineage |
| Customer satisfaction improvement is the main reason Q4 momentum will carry into 2026 | UNTRACEABLE | none | Causal claim with no supporting data |
| We now hold roughly 8% of the addressable market in our two largest regions | UNTRACEABLE | none | No market share or addressable market data in primary data or lineage |

