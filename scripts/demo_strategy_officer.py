"""
Phase 7 demo: unlike every prior demo script, this one does NOT fetch any
live data. The Chief Strategy Officer's whole job is to synthesize
AgentReports that OTHER agents already produced (see
scripts/demo_agents.py, demo_commodity_fx_agents.py, etc. for how those
individual departments fetch real data) — so the most honest way to
demonstrate ITS logic is with a set of illustrative example reports
representing a plausible real scenario, not live network calls.

This demo deliberately constructs a scenario where departments DISAGREE
(strong fundamental bulls, a cautious technical read, and a risk desk
flagging elevated portfolio risk) to show the disagreement-resolution math
actually doing something, rather than a scenario where everyone agrees and
the synthesis is trivial.

Run:
    python scripts/demo_strategy_officer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.chief_strategy_officer import ChiefStrategyOfficer
from models.report import AgentReport, Bias, RiskLevel, bias_from_score


def _report(department, bias_score, confidence, risk_level, catalysts=None, risks=None, evidence=None):
    return AgentReport(
        department=department,
        asset_or_theme="Gold",
        bias=bias_from_score(bias_score),
        bias_score=bias_score,
        confidence=confidence,
        risk_level=risk_level,
        catalysts=catalysts or [],
        risks=risks or [],
        evidence=evidence or [],
    )


def main():
    print("\n=== AI CFO Platform — Phase 7: Chief Strategy Officer demo ===")
    print("(Illustrative example department reports — see docs/ARCHITECTURE_PHASE7.md)\n")

    # A deliberately mixed picture: fundamentals bullish, technicals cautious,
    # and the risk desk flagging a crowded/volatile setup.
    reports = [
        _report(
            "Chief Macro Officer", bias_score=55, confidence=75, risk_level=RiskLevel.MODERATE,
            catalysts=["Disinflation trend supports continued policy easing expectations"],
            evidence=["CPI is decelerating (latest=305.2 as of 2026-06-01)"],
        ),
        _report(
            "Chief Commodity Analyst", bias_score=70, confidence=70, risk_level=RiskLevel.ELEVATED,
            catalysts=["Building speculative length reflects growing bullish conviction"],
            risks=["Net speculative positioning is a crowded long — vulnerable to a sharp reversal"],
        ),
        _report(
            "Chief Sentiment Officer", bias_score=40, confidence=55, risk_level=RiskLevel.MODERATE,
            catalysts=["Prevailing news flow is constructive"],
        ),
        _report(
            "Chief Technical Officer", bias_score=-30, confidence=65, risk_level=RiskLevel.ELEVATED,
            risks=["RSI(74.2) is overbought — vulnerable to a pullback"],
            evidence=["RSI(14) is 74.2", "Price structure shows an uptrend (20 SMA vs 50 SMA)"],
        ),
    ]

    risk_report = _report(
        "Chief Risk Officer", bias_score=0, confidence=70, risk_level=RiskLevel.ELEVATED,
        risks=["Portfolio volatility (28.4%) is elevated"],
    )

    officer = ChiefStrategyOfficer()
    result = officer.synthesize("Gold", reports, risk_report=risk_report)

    print(f"Overall Market Score: {result.overall_market_score}/100")
    print(f"Confidence Score:     {result.confidence_score}/100")
    print(f"Risk Level:           {result.risk_level.value}")
    print(f"Directional Bias:     {result.bias.value} (score {result.bias_score:+.1f})")
    print(f"\nContributing departments: {', '.join(result.contributing_departments)}")
    if result.excluded_departments:
        print(f"Excluded departments:     {', '.join(result.excluded_departments)}")

    print(f"\nTrade Thesis:\n  {result.trade_thesis}")

    print("\nCatalysts:")
    for c in result.catalysts:
        print(f"  - {c}")
    print("\nRisks:")
    for r in result.risks:
        print(f"  - {r}")
    print("\nInvalidation Notes:")
    for n in result.invalidation_notes:
        print(f"  - {n}")

    print(f"\nInvestment Committee Summary:\n  {result.investment_committee_summary}")


if __name__ == "__main__":
    main()
