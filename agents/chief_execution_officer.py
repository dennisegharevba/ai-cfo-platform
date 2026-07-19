"""
Chief Execution Officer — the twelfth and final Chief Officer.

Per the spec, this desk sends alerts ONLY when ALL of the following hold:
    - Confidence exceeds a configurable threshold
    - Macro/fundamentals/technical departments agree (captured here as
      "the synthesized bias is non-neutral" — the Chief Strategy Officer,
      Phase 7, has ALREADY resolved cross-department agreement/disagreement
      into overall_bias_score/confidence_score; the Execution Officer reads
      that resolved verdict rather than re-deriving agreement itself)
    - The risk model approves (risk_level at or below a configurable ceiling)
    - Required data is fresh and validated (captured as: not too many
      departments were excluded from the synthesis for lacking usable data)

This agent is architecturally similar to the Chief Strategy Officer: it
fetches no data of its own from DataIntegrityManager, it only reads a
StrategyReport that's already been produced. Its distinguishing job is
purely a gate — evaluate() never has side effects, and sending only
happens in process() after evaluate() has already said yes.
"""

from __future__ import annotations

from typing import List, Optional

from models.report import Bias, RiskLevel
from models.strategy_report import StrategyReport
from models.execution_decision import ExecutionDecision

from .risk_severity import SEVERITY_ORDER
from telegram.telegram_alerter import TelegramAlerter, TelegramError

DEFAULT_MIN_CONFIDENCE = 65.0
DEFAULT_MAX_ACCEPTABLE_RISK = RiskLevel.ELEVATED   # HIGH blocks by default; ELEVATED and below pass
DEFAULT_MIN_BIAS_MAGNITUDE = 15.0                  # matches bias_from_score's neutral band cutoff
DEFAULT_MAX_EXCLUDED_FRACTION = 0.5                # block if more than half of departments lacked usable data


class ChiefExecutionOfficer:
    department = "Chief Execution Officer"

    def __init__(
        self,
        alerter: Optional[TelegramAlerter] = None,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_acceptable_risk: RiskLevel = DEFAULT_MAX_ACCEPTABLE_RISK,
        min_bias_magnitude: float = DEFAULT_MIN_BIAS_MAGNITUDE,
        max_excluded_fraction: float = DEFAULT_MAX_EXCLUDED_FRACTION,
    ):
        self.alerter = alerter
        self.min_confidence = min_confidence
        self.max_acceptable_risk = max_acceptable_risk
        self.min_bias_magnitude = min_bias_magnitude
        self.max_excluded_fraction = max_excluded_fraction

    def evaluate(self, strategy_report: StrategyReport) -> ExecutionDecision:
        """
        Pure gate check — no side effects, never sends anything. Always
        returns a decision, including a fully-populated blocking_reasons
        list when should_alert is False, so a blocked cycle is just as
        auditable as a sent one.
        """
        blocking_reasons: List[str] = []

        if strategy_report.confidence_score < self.min_confidence:
            blocking_reasons.append(
                f"confidence {strategy_report.confidence_score:.1f} is below the "
                f"{self.min_confidence:.1f} threshold"
            )

        if strategy_report.bias == Bias.NEUTRAL or abs(strategy_report.bias_score) < self.min_bias_magnitude:
            blocking_reasons.append(
                f"bias ({strategy_report.bias.value}, score {strategy_report.bias_score:+.1f}) "
                f"is too weak/neutral to act on"
            )

        if SEVERITY_ORDER.index(strategy_report.risk_level) > SEVERITY_ORDER.index(self.max_acceptable_risk):
            blocking_reasons.append(
                f"risk level {strategy_report.risk_level.value} exceeds the acceptable "
                f"ceiling of {self.max_acceptable_risk.value}"
            )

        total_departments = len(strategy_report.contributing_departments) + len(strategy_report.excluded_departments)
        if total_departments > 0:
            excluded_fraction = len(strategy_report.excluded_departments) / total_departments
            if excluded_fraction > self.max_excluded_fraction:
                blocking_reasons.append(
                    f"{len(strategy_report.excluded_departments)} of {total_departments} departments "
                    f"lacked usable data this cycle — required data is not sufficiently fresh/validated"
                )

        return ExecutionDecision(
            asset_or_theme=strategy_report.asset_or_theme,
            should_alert=(len(blocking_reasons) == 0),
            blocking_reasons=blocking_reasons,
        )

    def format_alert_message(self, strategy_report: StrategyReport) -> str:
        """
        Per the spec: Asset, Bias, Confidence, Risk, Supporting evidence,
        Timestamp, Key reasons.
        """
        timestamp = strategy_report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"*{strategy_report.asset_or_theme}* — {strategy_report.bias.value.replace('_', ' ').upper()}",
            f"Overall Market Score: {strategy_report.overall_market_score:.0f}/100",
            f"Confidence: {strategy_report.confidence_score:.0f}/100",
            f"Risk Level: {strategy_report.risk_level.value.upper()}",
            f"Timestamp: {timestamp}",
            "",
            strategy_report.trade_thesis,
        ]
        if strategy_report.catalysts:
            lines.append("\nKey catalysts:")
            lines.extend(f"- {c}" for c in strategy_report.catalysts[:3])
        if strategy_report.risks:
            lines.append("\nKey risks:")
            lines.extend(f"- {r}" for r in strategy_report.risks[:3])
        return "\n".join(lines)

    def process(self, strategy_report: StrategyReport) -> ExecutionDecision:
        """
        evaluate() first; only if it passes AND an alerter is configured
        does this attempt to actually send. A configured alerter that
        fails to send does NOT get silently swallowed — the failure is
        recorded on the returned ExecutionDecision (send_error) so it's
        auditable, matching the platform's "never silently fail" principle
        used throughout the data-integrity layer.
        """
        decision = self.evaluate(strategy_report)
        if not decision.should_alert:
            return decision

        if self.alerter is None:
            return decision  # passed the gate, but nothing is configured to send through

        try:
            message = self.format_alert_message(strategy_report)
            self.alerter.send_message(message)
            decision.alert_sent = True
        except TelegramError as exc:
            decision.send_error = str(exc)

        return decision
