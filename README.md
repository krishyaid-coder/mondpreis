# mondpreis

<p align="center">
  <img src="img.png" alt="A duckling in a red cap" width="160">
</p>

Verify advertised price reductions against observed price history.

Status: the check itself runs. Live collection does not. See [Running](#running).

A *Mondpreis*, literally a moon price, is the German term for a reference price that was never seriously charged. A retailer lifts a price for a short period, then advertises a discount from the inflated figure. The discount is real arithmetic against a fictional baseline.

## Problem statement

Since May 2022, EU law has required that any announced price reduction state the lowest price the trader applied during at least the preceding 30 days. The obligation sits in Article 6a of Directive 98/6/EC, inserted by the Omnibus Directive (EU) 2019/2161, and is implemented in Germany as section 11 of the Preisangabenverordnung.

The Court of Justice tightened this in Case C-330/23 (Aldi Süd, 26 September 2024). An advertised percentage must be calculated from that 30 day low, not from the most recent or some older higher price. A footnote explaining the reference price does not cure the breach. The Bundesgerichtshof has since followed the same line.

The rule is therefore unusually well specified for a consumer protection obligation. It names a window, a statistic over that window, and an arithmetic relationship to the advertised figure. That makes compliance machine checkable, given price history.

Price history is the part nobody has.

## What the research established

Four checks were run before any design work. Two of them argue against the obvious version of this project, which is why they are recorded first.

**The headline report is already taken.** The European Commission and the consumer authorities of 23 member states plus Iceland and Norway publish coordinated sweeps. The most recent, published 26 March 2026 and covering the 2025 sales season, screened 314 traders and found roughly 30 percent displaying discounts incorrectly, with 34 percent showing price comparisons of which about six in ten failed to explain their methodology. The Commission uses an internal tool called EU eLab for the screening. Anyone planning to publish "the EU discount compliance report" is third in line behind an institution with enforcement powers.

**The litigation is taken too.** Verbraucherzentrale Baden-Württemberg brought the case that became C-330/23. The Verbraucherzentralen have sued Aldi, Lidl, Edeka and Netto over price advertising. They have standing and a track record. No Stiftung Warentest study on Streichpreise was found, so that specific slot appears open, but they could fill it whenever they choose.

**A snapshot sweep structurally cannot verify the rule it enforces.** This is the finding the project rests on. Deciding whether a given discount is lawful requires knowing the lowest price over the preceding 30 days. An inspection carried out during the sale window can only catch the visible failures, meaning no reference price shown, or arithmetic that does not add up on its face. It cannot detect a trader who raised the price three weeks earlier and then discounted from the inflated figure, because that evidence has already scrolled off the page. That is precisely the behaviour C-330/23 was decided to stop, and it is invisible without continuous history.

The Commission runs roughly one screening per year over about twelve traders per country, and publishes headline percentages. No public dataset, no methodology annex and no per trader results were found.

**No public dataset carries what this needs.** Open Prices by Open Food Facts is the closest candidate, ODbL licensed with a daily Parquet export carrying price, currency, date, store and barcode. It is crowdsourced grocery data, so it has the history half and none of the claim half. No struck through reference prices, no advertised percentages. The check requires both, since the entire question is whether the claim matches the history. This absence is the same gap viewed from the data side.

## The gap worth building into

Continuous, open, reproducible 30 day price history, used to evaluate advertised discount claims.

Not a better report. A dataset and a method that anyone can rerun and dispute. The contribution is the reproducible corpus and an honest limitations section, with the tool as a means to it.

Three properties make the narrow version tractable where a general comparison engine was not.

Each product is compared to its own past, never to another retailer's listing. That removes cross retailer product matching, which is the entity resolution problem that sinks most comparison projects and for which no open source solution was found.

The legal standard defines success numerically. There is no need to invent a quality metric or defend a threshold, because the Court already specified the window, the statistic and the arithmetic.

The scope is bounded by the calendar. Twenty to forty retailers and a few hundred product URLs is enough to be representative of a national market.

## Design

The engine is a pure function over a list of observations. It performs no collection and no network access, which is what makes it testable against constructed scenarios rather than against whatever the internet happened to be doing on the day.

### Data model

An observation records what one product page showed on one day. Crucially it keeps the retailer's claim separate from any derived figure. The current price, the struck through reference price if shown, and the advertised percentage if shown are all recorded as claims. Everything else the engine computes itself. That separation is what makes a finding defensible, because the retailer's own numbers can always be displayed next to the history they contradict.

Money is `Decimal`, never `float`. A float cannot represent 19.99 exactly and the engine's whole purpose is comparing prices and deriving percentages from them. Float drift would produce findings wrong by a cent, which is indistinguishable from a bug in the legal logic.

Dates are days, not timestamps. The rule is written in days, so a day is the natural unit and timezone handling becomes a problem the project does not need to have.

### The central modelling decision

Discount claims are grouped into episodes, meaning consecutive runs of days on which a reduction was advertised. The 30 day window is anchored to the day the episode started, not to each day inside it.

This exists because of a trap that is easy to fall into and hard to notice. A naive implementation takes the lookback from whichever day it is examining. By day three of a sale the reduced price is itself inside the window, becomes the window low, and the violation quietly disappears. Every sale ends up vouching for its own legality the longer it runs. Anchoring to the episode start is what prevents it.

Episodes also need a gap tolerance, so that a collector which misses a Sunday does not split one sale into two.

### Checks

| Check | Provision | Severity |
|---|---|---|
| Reduction announced with no prior price shown | Art. 6a(1) | error |
| Stated prior price exceeds the observed 30 day low | Art. 6a(2) | error |
| Advertised percentage not derived from the 30 day low | C-330/23 | error |
| Prior price in effect only briefly, with cheaper prices behind it | misleading practice test | warning |
| Fewer than 30 days of usable history | not evaluable | info |

The last row matters more than it looks. If the engine cannot verify a claim it must say so explicitly, because returning no findings would be read as a clean bill of health. Reporting insufficient history is the difference between a measurement and a reassurance.

The warning row is deliberately not an error. A briefly held reference price is evidence of the behaviour the rule exists to stop, but it is not a per se breach, and the project loses its credibility the moment it starts asserting infringements it cannot establish.

### Known blind spot

Article 6a(2) sets 30 days as a floor, not a fixed window. A trader who lifts a price and holds the inflated figure for longer than 30 days satisfies the arithmetic exactly. The engine will report nothing, correctly, and the consumer is still misled.

Catching this needs a longer lookback, which is a judgement call rather than a legal one. It belongs in a report's limitations section, not in a quietly adjusted threshold. The design keeps this as a named scenario so it stays visible rather than becoming folklore.

### Why synthetic data first

The check is a pure function over a time series, so it is fully testable without a single real observation. Three reasons this is the right order rather than a shortcut.

Real collection imposes a 30 day wait before anything can be tested at all. Synthetic histories can be constructed and evaluated immediately.

Scenarios can reproduce the case law deliberately. Real data may simply not contain a clean instance of the Aldi Süd pattern during the period observed, whereas a constructed scenario contains exactly one and nothing else.

The scenarios become the specification. Expected findings are derivable from the statute and the judgment rather than from whatever the engine currently does, which keeps the engine answerable to the law instead of to its own output.

Planned scenarios, each with findings derivable from the law: a compliant sale producing nothing, the textbook inflation, the Aldi Süd pattern, a bare percentage with no reference shown, a late starting collector, and the window gaming blind spot above.

## Collection, if it ever happens

Not required for the engine. Recorded because the legal position was researched and should not be lost.

The German position on collecting public prices is mixed but workable for this specific design, and notably worse for a general comparison engine. Germany implements the EU Database Directive in sections 87a and 87b UrhG, where protection depends on substantial investment, and a German decision on automated evaluation of an online car marketplace found no infringement because the database maker's investment in those particular listings was absent. The Bundesgerichtshof has held that screen scraping is not by itself an act of unfair competition.

The important asymmetry is Innoweb, CJEU C-202/12, which holds that meta search engines can infringe the database right of the sites they index. That is aimed squarely at a comparison engine. A compliance monitor that retains one retailer's own price history and competes with nobody sits well outside it.

Practical constraints, none of them optional. Respect robots.txt, since section 44b UrhG makes a machine readable opt out effective against commercial text and data mining. Keep request rates low. Store prices only and never personal data, which keeps GDPR out of scope. Never defeat a technical access barrier, which is what brings section 202a StGB into play. Publish the method, because transparency is the best available defence.

All of the above is drawn from law firm commentary and secondary sources, not primary law, and none of it is cleared advice. Naming individual retailers in a published result is the point at which an hour with a German lawyer becomes worth paying for.

## Open questions

Whether any national regulator intends to publish compliance rates on a recurring basis. If UOKiK or a German authority starts doing this quarterly, the project is obsoleted and should be abandoned rather than defended.

Whether a consumer organisation has systematic monitoring underway. The Verbraucherzentralen and Stiftung Warentest are the natural homes for this and carry authority the project cannot.

Primary source confirmation of the sweep figures. Press reports conflict, with one outlet reporting 60 percent of businesses applying irregular discounts against the Commission's 30 percent, and sample sizes quoted as both 314 and 356. The 60 percent is probably the sub figure about unexplained comparison methodology being misread, but this was not verified against the primary release. Any report that cites these numbers wrongly forfeits the credibility it is trying to build.

## Why this location is useful

Trier sits where Germany, Luxembourg, Belgium and France meet. The directive is EU law implemented nationally, so enforcement intensity and national transposition differ across those four. Running one method against retailers in all of them produces cross border divergence that a single market vantage point would not generate.

## Running

The environment is managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run mondpreis scenarios
uv run mondpreis check observations.json
```

`scenarios` evaluates the synthetic histories in `src/mondpreis/synthetic.py`. `check` reads a JSON list of observations. Prices are strings (`"19.99"`), never JSON numbers, so a float cannot enter the arithmetic. The process exits 1 when any finding has severity `error`.

## Repository state

The engine, the synthetic scenarios, and the test suite run. `uv run pytest` is the check that the implementation still matches the specification above. Collection of live prices is still out of scope.

## Legal note

Not legal advice. A finding from this engine means that a retailer's advertised figures contradict their own observed price history, which is a factual claim about data. Whether any instance is an infringement is a matter for a regulator or a court.

## References

Directive 98/6/EC Article 6a, as inserted by Directive (EU) 2019/2161.
Preisangabenverordnung section 11 (Germany).
CJEU Case C-330/23, Aldi Süd, 26 September 2024.
CJEU Case C-202/12, Innoweb.
[European Commission sweep results, 26 March 2026](https://commission.europa.eu/news-and-media/news/eu-check-reveals-misleading-sales-practices-online-2026-03-26_en)
[CCPC summary of the same sweep](https://www.ccpc.ie/news-and-media/news/article/2026/03/26/investigation-by-ec--ccpc-and-european-consumer-authorities-finds-1-in-3-traders-incorrectly-display-discounts-online-during-black-friday-sales)
[Commission sweeps programme](https://commission.europa.eu/topics/consumers/consumer-rights-and-complaints/enforcement-consumer-protection/sweeps_de)
[Open Prices dataset](https://data.gouv.fr/en/datasets/open-prices)
[Öko-Test on the 30 day best price ruling](https://www.oekotest.de/geld-versicherungen/Urteil-Nicht-mehr-ohne-den-30-Tage-Bestpreis-_15395_1.html)
[BGH following the CJEU line](https://www.biallo.de/recht-steuern/news/schluss-mit-mogel-rabatten-bgh-urteil-zu-streichpreisen-schuetzt-verbraucher/)
[Verbraucherzentrale actions against supermarket chains](https://www.berliner-kurier.de/article/aldi-lidl-edeka-und-netto-verklagt-verbraucherzentrale-sauer-auf-supermarkt-riesen-326402)
[Database right analysis, sections 87a and 87b UrhG](https://lxgesetze.de/urhg/87b)
[German case on automated evaluation of an online database](https://betriebs-berater.ruw.de/wirtschaftsrecht/urteile/Zur-automatisierten-Auswertung-von-Online-Datenbanken---Automobil-Onlineboerse-17656)
[BGH on screen scraping and unfair competition](https://husovec.eu/?p=53)
[Section 44b UrhG and text and data mining](https://www.wbs.legal/urheberrecht/ist-screen-scraping-legal-15081/)
