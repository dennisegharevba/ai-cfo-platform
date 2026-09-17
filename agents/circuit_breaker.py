"""
Circuit breaker — pure, stateless threshold logic determining whether
trading should HALT given current account equity relative to a daily
starting value and an all-time peak.

Deliberately pure: this module never places, cancels, or touches any
order itself. It only answers "should trading be halted right now, and
why" — the ACTION taken on a halt (blocking new orders, sending an
alert) belongs to whatever calls this, not to the breaker itself. This
keeps the safety-critical threshold math independently testable and
free of any side effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CircuitBreakerConfig:
    max_daily_loss_pct: float = 5.0     # halt if today's equity has fallen this much from today's starting equity
    max_total_drawdown_pct: float = 15.0  # halt if equity has fallen this much from its all-time peak


@dataclass
class CircuitBreakerResult:
    should_halt: bool
    daily_pnl_pct: float
    drawdown_from_peak_pct: float
    reasons: List[str] = field(default_factory=list)


def check_circuit_breaker(
    current_equity: float, daily_starting_equity: float, peak_equity: float,
    config: CircuitBreakerConfig = None,
) -> CircuitBreakerResult:
    """
    current_equity: right now.
    daily_starting_equity: equity at the start of today — the reference
        point for the daily-loss check. Resets once per day; tracking
        that reset is the caller's responsibility (this function is
        stateless and takes whatever value it's given).
    peak_equity: the highest equity value ever observed — the reference
        point for the total-drawdown check. Also caller-tracked.

    Both checks are evaluated independently — either alone can trigger a
    halt, and both reasons are reported if both are breached
    simultaneously, not just the first one found.
    """
    config = config or CircuitBreakerConfig()
    reasons = []

    daily_pnl_pct = ((current_equity - daily_starting_equity) / daily_starting_equity * 100) if daily_starting_equity > 0 else 0.0
    drawdown_from_peak_pct = ((current_equity - peak_equity) / peak_equity * 100) if peak_equity > 0 else 0.0

    if daily_pnl_pct <= -config.max_daily_loss_pct:
        reasons.append(
            f"Daily loss {daily_pnl_pct:.2f}% has reached or exceeded the "
            f"{config.max_daily_loss_pct}% daily loss limit"
        )
    if drawdown_from_peak_pct <= -config.max_total_drawdown_pct:
        reasons.append(
            f"Drawdown from peak equity {drawdown_from_peak_pct:.2f}% has reached or exceeded the "
            f"{config.max_total_drawdown_pct}% max drawdown limit"
        )

    return CircuitBreakerResult(
        should_halt=len(reasons) > 0, daily_pnl_pct=round(daily_pnl_pct, 3),
        drawdown_from_peak_pct=round(drawdown_from_peak_pct, 3), reasons=reasons,
    )
