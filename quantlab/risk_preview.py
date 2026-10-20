"""Deterministic MNQ risk-sizing preview. Research only; never creates orders.

Inspired by the separation of budget/risk/order approval in trader-skill (MIT),
reimplemented for MNQ futures rather than stocks or broker execution.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from .market import Contract

_ALLOWED = {
    "contract_id", "direction", "stop_ticks", "risk_budget_usd", "max_session_loss_usd",
    "session_realised_loss_usd", "round_trip_fee_usd", "slippage_ticks",
    "existing_contracts", "available_cash_usd", "assumed_margin_per_contract_usd",
}


def _amount(value: object, name: str, *, zero: bool = True) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name} must be a finite numeric value")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not number.is_finite() or number < 0 or (not zero and number == 0) or number > Decimal("1000000000"):
        raise ValueError(f"{name} is outside its permitted range")
    return number


def _whole(value: object, name: str, *, positive: bool = False, maximum: int = 1000000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0) or value > maximum:
        raise ValueError(f"{name} must be a bounded integer")
    return value


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_CEILING))


def assess_proposal(proposal: dict, contract: Contract | None = None) -> dict:
    """Review one hypothetical 1-contract MNQ exposure, not a trade permission.

    Round estimated loss *up* to cents. A fixed-distance stop does not guarantee
    a fill; the estimate is conditional on the supplied adverse slippage.
    """
    if not isinstance(proposal, dict) or set(proposal) - _ALLOWED:
        raise ValueError("Proposal must be an object with only recognised research fields")
    contract = contract or Contract()
    if proposal.get("contract_id") != contract.contract_id:
        raise ValueError("Contract ID must match the selected MNQ instrument")
    if contract.symbol != "MNQ" or contract.currency != "USD":
        raise ValueError("This risk preview only supports USD MNQ contracts")
    if proposal.get("direction") not in ("long", "short"):
        raise ValueError("direction must be long or short")
    stop = _whole(proposal.get("stop_ticks"), "stop_ticks", positive=True, maximum=100000)
    slip = _whole(proposal.get("slippage_ticks", 2), "slippage_ticks", maximum=10000)
    existing = _whole(proposal.get("existing_contracts", 0), "existing_contracts", maximum=1)
    budget = _amount(proposal.get("risk_budget_usd"), "risk_budget_usd", zero=False)
    daily_limit = _amount(proposal.get("max_session_loss_usd"), "max_session_loss_usd", zero=False)
    loss_so_far = _amount(proposal.get("session_realised_loss_usd"), "session_realised_loss_usd")
    fees = _amount(proposal.get("round_trip_fee_usd", "3.00"), "round_trip_fee_usd")
    if ("available_cash_usd" in proposal) != ("assumed_margin_per_contract_usd" in proposal):
        raise ValueError("Margin assumption and available cash must both be supplied, or neither")
    cash = margin = None
    if "available_cash_usd" in proposal:
        cash = _amount(proposal["available_cash_usd"], "available_cash_usd")
        margin = _amount(proposal["assumed_margin_per_contract_usd"], "assumed_margin_per_contract_usd", zero=False)
    tick_value = Decimal(str(contract.tick_value))
    # Stop distance + adverse entry AND exit slippage + total round-trip fees.
    risk = Decimal(stop) * tick_value + 2 * Decimal(slip) * tick_value + fees
    risk = risk.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    headroom = max(Decimal(0), daily_limit - loss_so_far)
    cap = min(budget, headroom)
    reasons = []
    if existing:
        reasons.append("One-contract research cap already occupied")
    if headroom == 0:
        reasons.append("Session loss limit exhausted")
    if risk > cap:
        reasons.append("Estimated loss including costs exceeds remaining research risk budget")
    if cash is not None and cash < margin:
        reasons.append("Cash below user-supplied illustrative margin assumption")
    allowed = not reasons
    canonical = json.dumps(proposal, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {
        "status": "within_research_limits" if allowed else "blocked",
        "proposed_contracts": 1 if allowed else 0,
        "contract_id": contract.contract_id,
        "direction": proposal["direction"],
        "per_contract_estimated_loss_usd": _money(risk),
        "budget_cap_usd": _money(cap),
        "session_loss_headroom_usd": _money(headroom),
        "assumed_margin_usd": _money(margin) if margin is not None else None,
        "proposal_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "reasons": reasons,
        "warnings": [
            "Research preview only: no broker integration, orders, permission or paper promotion",
            "Stop distance is hypothetical; gaps, liquidity and execution can exceed assumed slippage",
            "Session means the user's declared risk window, not an independently verified CME session",
            "Margin is an unverified user assumption" if margin is not None else "Margin adequacy not assessed",
        ],
        "eligible_for_paper": False,
        "eligible_for_live": False,
    }
