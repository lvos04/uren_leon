"""Bruto-netto schatting voor het vaste maandsalaris (niet voor overuren: die zijn netto).

Werkwijze: maandloon x 12 = jaarloon -> belasting volgens de schijven -> min algemene heffingskorting
en arbeidskorting (alleen als loonheffingskorting = ja) -> / 12. Dit is een benadering van de
loonheffing; de loonstrook kan enkele euro's afwijken.
"""
import json
from pathlib import Path

RATES = {k: v for k, v in json.loads((Path(__file__).parent / "tax_rates.json").read_text()).items()
         if not k.startswith("_")}
SITUATIES = {"standard": "Jonger dan de AOW-leeftijd",
             "aow": "AOW-leeftijd en ouder (geboren 1946 of later)"}


def available_years() -> list[int]:
    return sorted(int(y) for y in RATES)


def rates_for(year: int) -> tuple[int, dict]:
    years = available_years()
    use = max([y for y in years if y <= year], default=years[0])
    return use, RATES[str(use)]


def _bracket_tax(income: float, brackets) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in brackets:
        top = income if upper is None else min(income, upper)
        if top > lower:
            tax += (top - lower) * rate
        if upper is None or income <= upper:
            break
        lower = upper
    return tax


def _ahk(income: float, p: dict) -> float:
    return max(0.0, p["max"] - max(0.0, income - p["start"]) * p["rate"])


def _ak(income: float, segments) -> float:
    lower = 0.0
    for upper, base, rate in segments:
        if income <= upper:
            return max(0.0, base + (income - lower) * rate)
        lower = upper
    return 0.0


def bruto_netto(bruto_maand: float, year: int, loonheffingskorting: bool = True,
                situatie: str = "standard", pensioen_maand: float = 0.0,
                overig_maand: float = 0.0) -> dict:
    """pensioen_maand: inhouding voor belasting (verlaagt het belastbaar loon).
    overig_maand: inhoudingen na belasting (bv. personeelsvereniging)."""
    used_year, table = rates_for(year)
    t = table.get(situatie, table["standard"])
    jaar = max(0.0, (bruto_maand - pensioen_maand) * 12)
    belasting = _bracket_tax(jaar, t["brackets"])
    ahk = _ahk(jaar, t["ahk"]) if loonheffingskorting else 0.0
    ak = _ak(jaar, t["ak"]) if loonheffingskorting else 0.0
    # kortingen kunnen niet meer zijn dan de belasting
    kortingen = min(belasting, ahk + ak)
    ak_eff = min(ak, kortingen)
    ahk_eff = kortingen - ak_eff
    netto_jaar = jaar - belasting + kortingen - overig_maand * 12
    m = lambda v: round(v / 12, 2)
    return dict(
        tarief_jaar=used_year,
        bruto=round(bruto_maand, 2),
        pensioen=round(pensioen_maand, 2),
        overig=round(overig_maand, 2),
        loonbelasting=m(belasting),
        algemene_heffingskorting=m(ahk_eff),
        arbeidskorting=m(ak_eff),
        netto=m(netto_jaar),
        netto_pct=(netto_jaar / (bruto_maand * 12)) if bruto_maand else 0,
        druk=m(belasting - kortingen),
        druk_pct=((belasting - kortingen) / (bruto_maand * 12)) if bruto_maand else 0,
    )
