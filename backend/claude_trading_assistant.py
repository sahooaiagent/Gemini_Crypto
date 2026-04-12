"""
Claude Trading Assistant — Enterprise Edition
===============================================
Powered by Claude Opus 4.6 (adaptive thinking + streaming)

Three enterprise-grade AI capabilities:

  1. analyze_trade_decision()      — Multi-factor confluence scoring, Kelly Criterion
                                     position sizing, regime detection, full trade playbook
  2. improve_pine_script()         — Iterative Pine Script v6 builder with structured
                                     per-iteration feedback, early-stop at confidence ≥ 0.95
  3. validate_scalping_strategy()  — Adversarial multi-round stress-tester targeting
                                     90%+ win rate with Sharpe/drawdown/regime analysis

Requirements
------------
  pip install anthropic pydantic
  export ANTHROPIC_API_KEY=sk-ant-...

Usage
-----
  from claude_trading_assistant import (
      analyze_trade_decision,
      improve_pine_script,
      validate_scalping_strategy,
  )
"""

import os
import re
import json
import datetime
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────
client = anthropic.Anthropic()
MODEL  = "claude-opus-4-6"


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ENTERPRISE SCHEMAS
# ═════════════════════════════════════════════════════════════════════════════

class ConfluenceFactor(BaseModel):
    """One contributing signal in the confluence score."""
    name:        str
    weight:      float = Field(ge=0.0, le=1.0)
    aligned:     bool
    description: str


class RiskProfile(BaseModel):
    """Position sizing and risk metrics."""
    position_size_usd:    float
    position_size_pct:    float   = Field(description="% of account")
    kelly_fraction:       float   = Field(description="Kelly Criterion fraction (0–1)")
    max_loss_usd:         float
    reward_usd_tp1:       float
    reward_usd_tp2:       float
    risk_reward_tp1:      float
    risk_reward_tp2:      float


class TradePlaybook(BaseModel):
    """Step-by-step execution instructions."""
    pre_entry_checklist:  list[str]
    entry_instruction:    str
    stop_loss_instruction: str
    tp1_instruction:      str
    tp2_instruction:      str
    invalidation_rules:   list[str]
    trade_management:     list[str]


class EnterpriseTradeDecision(BaseModel):
    """Full enterprise trade decision with multi-factor analysis."""
    symbol:               str
    action:               str    = Field(description="BUY | SELL | HOLD | WAIT")
    confidence:           float  = Field(ge=0.0, le=1.0)
    market_regime:        str    = Field(description="TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOLATILITY | LOW_LIQUIDITY")
    confluence_score:     float  = Field(ge=0.0, le=1.0, description="Weighted confluence of all signals")
    confluence_factors:   list[ConfluenceFactor]
    entry_price:          Optional[float] = None
    stop_loss:            Optional[float] = None
    take_profit_1:        Optional[float] = None
    take_profit_2:        Optional[float] = None
    take_profit_3:        Optional[float] = None
    risk_profile:         Optional[RiskProfile] = None
    playbook:             Optional[TradePlaybook] = None
    primary_reasoning:    str
    supporting_evidence:  list[str]
    counter_arguments:    list[str]
    warnings:             list[str]
    skip_trade_if:        list[str]   = Field(description="Conditions that invalidate this setup")
    best_entry_window:    Optional[str] = Field(default=None, description="e.g. 'Next 15-min candle open after confirmation'")
    timeframe_alignment:  str   = Field(description="Which timeframes agree / disagree")


class PineScriptIteration(BaseModel):
    """Structured result of one Pine Script improvement round."""
    iteration:            int
    compile_errors_found: list[str]
    compile_errors_fixed: list[str]
    logic_improvements:   list[str]
    performance_fixes:    list[str]
    nan_fixes:            list[str]
    remaining_issues:     list[str]
    confidence_score:     float  = Field(ge=0.0, le=1.0, description="Claude's own assessment")
    ready_for_production: bool
    script:               str    = Field(description="Complete, standalone Pine Script v6 code")


class MarketConditionResult(BaseModel):
    """Win-rate estimate for a specific market condition."""
    condition:       str
    win_rate:        float = Field(ge=0.0, le=1.0)
    sample_size_est: int
    notes:           str


class EnterpriseScalpingValidation(BaseModel):
    """One adversarial validation round of a scalping strategy."""
    iteration:           int
    overall_win_rate:    float  = Field(ge=0.0, le=1.0)
    risk_reward_ratio:   float
    sharpe_ratio_est:    float
    max_drawdown_pct:    float
    profit_factor:       float
    is_profitable:       bool
    market_conditions:   list[MarketConditionResult]
    critical_weaknesses: list[str]
    improvements_made:   list[str]
    new_rules_added:     list[str]
    rules_removed:       list[str]
    verdict:             str
    next_focus:          str   = Field(description="What to fix next iteration")


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ENTERPRISE TRADE DECISION ANALYZER
# ═════════════════════════════════════════════════════════════════════════════

_TRADE_SYSTEM = """\
You are a senior quantitative crypto trader managing an enterprise trading desk.
You have 20+ years across HFT, systematic scalping, and swing trading on BTC, ETH, and altcoin futures.

ENTERPRISE DECISION FRAMEWORK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CONFLUENCE SCORING
   Score each signal 0–1 by alignment and weight. Minimum 3 signals must align
   before action = BUY or SELL. Fewer → WAIT. Conflicting HTF → HOLD.

2. MARKET REGIME DETECTION
   Classify regime BEFORE entry logic:
   • TRENDING_UP / TRENDING_DOWN → follow momentum, wider stops, trail TP2
   • RANGING → fade extremes, tighter stops, quick TP1
   • HIGH_VOLATILITY → halve position size, widen stops by 1.5×
   • LOW_LIQUIDITY → skip or use limit orders only

3. KELLY CRITERION POSITION SIZING
   kelly_f = (win_rate × rr - (1 - win_rate)) / rr
   Use half-Kelly for crypto (capped at 5% account risk per trade).
   In HIGH_VOLATILITY regime: cap at 2%.

4. RISK / REWARD REQUIREMENTS
   • Scalping (< 30min TF): min R:R = 1.5:1
   • Intraday (1h–4h TF):   min R:R = 2:1
   • Swing (1D+):            min R:R = 3:1
   Reject the trade if R:R does not meet the threshold for the timeframe.

5. STOP-LOSS PLACEMENT
   Use ATR-based OR structural stops (recent swing high/low), whichever is more
   conservative. Never place stops at round numbers.

6. CONFIDENCE CALIBRATION
   • 0.90–1.00: All major signals align across 3+ timeframes → STRONG
   • 0.75–0.89: 2 timeframes align, minor divergence → MODERATE
   • 0.60–0.74: 1 timeframe strong, others neutral → WEAK
   • < 0.60: Conflicting signals → WAIT

7. WARNINGS & INVALIDATION
   Always list: macro news risk, low-volume windows (midnight UTC, weekends),
   conflicting HTF signals, and exact conditions that kill the setup.

Be conservative. A missed trade costs nothing. A bad trade costs real money.
"""

def analyze_trade_decision(
    symbol:             str,
    signals:            list[dict],
    current_price:      float,
    timeframe:          str   = "15min",
    account_size:       float = 10_000.0,
    risk_per_trade_pct: float = 1.0,
    win_rate_estimate:  float = 0.62,
) -> EnterpriseTradeDecision:
    """
    Enterprise multi-factor trade decision using Claude Opus 4.6.

    Parameters
    ----------
    symbol             : e.g. "BTCUSDT.P"
    signals            : list of scanner signal dicts
    current_price      : current mark/last price
    timeframe          : primary chart timeframe
    account_size       : trading account size USD
    risk_per_trade_pct : max risk per trade as % of account
    win_rate_estimate  : historical win rate for Kelly sizing (default 62%)

    Returns
    -------
    EnterpriseTradeDecision
    """
    rr_target     = 2.0
    kelly_raw     = (win_rate_estimate * rr_target - (1 - win_rate_estimate)) / rr_target
    kelly_half    = max(0.0, kelly_raw / 2)
    max_risk_pct  = min(kelly_half, risk_per_trade_pct / 100)
    max_risk_usd  = account_size * max_risk_pct
    signals_json  = json.dumps(signals, indent=2)
    utc_now       = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    response = client.messages.parse(
        model      = MODEL,
        max_tokens = 8_192,
        thinking   = {"type": "adaptive"},
        system     = _TRADE_SYSTEM,
        messages   = [{
            "role":    "user",
            "content": f"""\
ENTERPRISE TRADE ANALYSIS REQUEST
══════════════════════════════════
Symbol        : {symbol}
Current Price : {current_price:,.4f}
Primary TF    : {timeframe}
Account Size  : ${account_size:,.2f}
Max Risk/Trade: ${max_risk_usd:,.2f}  (Half-Kelly={kelly_half:.1%}, capped at {risk_per_trade_pct}%)
Win Rate Est. : {win_rate_estimate:.0%}
UTC Time      : {utc_now}

SCANNER SIGNALS:
{signals_json}

REQUIRED ANALYSIS:
1. Classify market regime (TRENDING_UP/DOWN, RANGING, HIGH_VOLATILITY, LOW_LIQUIDITY)
2. Score each signal as a confluence factor (name, weight 0–1, aligned true/false)
3. Calculate weighted confluence score
4. Determine action: BUY / SELL / HOLD / WAIT with confidence 0–1
5. Set precise entry, stop-loss (ATR or structural), TP1, TP2, TP3
6. Calculate risk profile: position size (USD + % of account), R:R for each TP
7. Write step-by-step trade playbook (pre-entry checklist → trade management)
8. List supporting evidence, counter-arguments, and exact invalidation conditions
9. Specify best entry window timing
10. Summarise timeframe alignment (which agree / which conflict)
""",
        }],
        output_format = EnterpriseTradeDecision,
    )

    return response.parsed_output


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ENTERPRISE PINE SCRIPT BUILDER (streaming, structured, iterative)
# ═════════════════════════════════════════════════════════════════════════════

_PINE_SYSTEM = """\
You are a world-class TradingView Pine Script v6 developer and quantitative analyst.
You build production-grade indicators that are deployed on live trading desks.

HARD RULES — NEVER BREAK:
1. Pine Script v6 syntax ONLY. Zero deprecated v3/v4/v5 calls.
2. `var` for ALL persistent variables.
3. Every user option declared with `input.*()`.
4. ALL NaN/na values guarded with `nz()` or explicit na-checks before arithmetic.
5. `alertcondition()` for EVERY buy/sell/exit signal.
6. `max_bars_back` set on any series accessed with offset > 500.
7. No `security()` calls without `lookahead=barmerge.lookahead_off`.
8. Every response: ONE complete, standalone, compile-ready script in ```pine ... ``` block.
9. After the code block: structured JSON in ```json ... ``` block with these fields:
   {
     "compile_errors_found": [...],
     "compile_errors_fixed": [...],
     "logic_improvements":   [...],
     "performance_fixes":    [...],
     "nan_fixes":            [...],
     "remaining_issues":     [...],
     "confidence_score":     0.0–1.0,
     "ready_for_production": true/false
   }

QUALITY STANDARDS:
• Adaptive lengths: auto-scale with timeframe (shorter on 1m–5m, longer on 4h+)
• Visualisation: clear signal arrows, background colours, info table in corner
• Performance: avoid redundant recalculations, use `ta.*` built-ins over manual loops
• Robustness: handle edge cases (low volume, gap opens, first bars)
• Documentation: inline comments on non-obvious logic only
"""

def _extract_pine_script(text: str) -> str:
    """Extract Pine Script code from markdown fenced block."""
    m = re.search(r"```(?:pine(?:script|-script)?)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _extract_pine_metadata(text: str) -> dict:
    """Extract the structured JSON metadata block after the Pine Script."""
    m = re.search(r"```json\s*\n(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return {}


def improve_pine_script(
    description:     str,
    existing_script: Optional[str] = None,
    iterations:      int            = 5,
    print_progress:  bool           = True,
) -> list[PineScriptIteration]:
    """
    Enterprise iterative Pine Script builder using Claude Opus 4.6.

    Each iteration Claude:
    1. Reviews compile errors, deprecated calls, NaN/na edge cases
    2. Improves signal logic, adaptive parameters, visualisation
    3. Outputs structured metadata JSON alongside the script
    4. Stops early when confidence ≥ 0.95 AND ready_for_production = true

    Parameters
    ----------
    description     : plain-English spec of what the indicator must do
    existing_script : optional starting script to improve
    iterations      : max improvement rounds (default 5)
    print_progress  : stream output to stdout

    Returns
    -------
    list[PineScriptIteration] — one entry per iteration
    """
    results:       list[PineScriptIteration] = []
    history:       list[dict]                = []
    current_script = existing_script or ""

    for i in range(1, iterations + 1):
        if print_progress:
            print(f"\n{'═'*60}", flush=True)
            print(f"  PINE SCRIPT — Iteration {i}/{iterations}", flush=True)
            print(f"{'═'*60}", flush=True)

        # Build user message
        if i == 1 and not existing_script:
            user_msg = f"""\
Build a production-grade Pine Script v6 indicator matching this specification:

{description}

Deliver:
1. ONE complete, standalone script in a ```pine … ``` block
2. Structured metadata JSON in a ```json … ``` block immediately after

Quality bar: the script must compile on TradingView without any errors or warnings."""

        elif i == 1 and existing_script:
            user_msg = f"""\
Review and upgrade this Pine Script indicator to match the spec below.

SPECIFICATION:
{description}

EXISTING SCRIPT TO IMPROVE:
```pine
{existing_script}
```

Audit every line for:
• Pine Script v6 compile errors or deprecated calls
• Logic gaps vs. the specification
• Missing NaN/na guards
• Redundant calculations
• Missing alertcondition() calls

Then deliver:
1. The fully corrected script in a ```pine … ``` block
2. Structured metadata JSON in a ```json … ``` block"""

        else:
            prev = results[-1]
            issues_str = "\n".join(f"  - {x}" for x in prev.remaining_issues) or "  None reported"
            user_msg = f"""\
Iteration {i} — adversarial review of the previous script.

PREVIOUS METRICS:
  Confidence     : {prev.confidence_score:.0%}
  Ready for prod : {prev.ready_for_production}
  Remaining issues:
{issues_str}

```pine
{current_script}
```

Focus this round on:
1. Any remaining compile errors or Pine Script v6 violations
2. Edge cases not yet handled (first bars, zero volume, gap opens)
3. Signal accuracy — are the crossover conditions mathematically correct?
4. Adaptive parameters — do lengths scale correctly across all timeframes?
5. Visualisation completeness — arrows, backgrounds, info table, tooltips

Deliver:
1. The improved script in a ```pine … ``` block
2. Updated metadata JSON in a ```json … ``` block"""

        history.append({"role": "user", "content": user_msg})

        # Streaming call
        full_text = ""
        with client.messages.stream(
            model      = MODEL,
            max_tokens = 16_384,
            thinking   = {"type": "adaptive"},
            system     = _PINE_SYSTEM,
            messages   = history,
        ) as stream:
            for chunk in stream.text_stream:
                full_text += chunk
                if print_progress:
                    print(chunk, end="", flush=True)

        if print_progress:
            print(flush=True)

        # Extract script and metadata
        script   = _extract_pine_script(full_text)
        metadata = _extract_pine_metadata(full_text)

        result = PineScriptIteration(
            iteration            = i,
            compile_errors_found = metadata.get("compile_errors_found", []),
            compile_errors_fixed = metadata.get("compile_errors_fixed", []),
            logic_improvements   = metadata.get("logic_improvements", []),
            performance_fixes    = metadata.get("performance_fixes", []),
            nan_fixes            = metadata.get("nan_fixes", []),
            remaining_issues     = metadata.get("remaining_issues", []),
            confidence_score     = float(metadata.get("confidence_score", 0.60 + i * 0.07)),
            ready_for_production = bool(metadata.get("ready_for_production", False)),
            script               = script,
        )
        results.append(result)
        current_script = script

        history.append({
            "role":    "assistant",
            "content": f"[Iteration {i}: confidence={result.confidence_score:.0%}, "
                       f"ready={result.ready_for_production}, "
                       f"remaining issues={len(result.remaining_issues)}]",
        })

        if print_progress:
            status = "✅ PRODUCTION READY" if result.ready_for_production else "🔄 Needs more work"
            print(f"\n  {status}", flush=True)
            print(f"  Confidence       : {result.confidence_score:.0%}", flush=True)
            print(f"  Compile fixes    : {len(result.compile_errors_fixed)}", flush=True)
            print(f"  Logic improve.   : {len(result.logic_improvements)}", flush=True)
            print(f"  Remaining issues : {len(result.remaining_issues)}", flush=True)
            if result.remaining_issues:
                for iss in result.remaining_issues[:3]:
                    print(f"    • {iss}", flush=True)

        if result.confidence_score >= 0.95 and result.ready_for_production:
            if print_progress:
                print(f"\n  🎯 Target reached — stopping at iteration {i}", flush=True)
            break

    return results


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — ENTERPRISE SCALPING STRATEGY VALIDATOR
# ═════════════════════════════════════════════════════════════════════════════

_SCALPING_SYSTEM = """\
You are a professional quantitative researcher and adversarial strategy tester.
You have stress-tested hundreds of crypto scalping strategies across 5 years of data.

YOUR JOB: Find every possible way this strategy can fail before it costs real money.

VALIDATION FRAMEWORK
━━━━━━━━━━━━━━━━━━━

ROUND 1 — BASELINE ASSESSMENT
  • Win rate estimate (realistic, accounting for fees 0.04% maker / 0.06% taker)
  • Profit factor = gross profit / gross loss (need > 1.5)
  • Sharpe ratio estimate (daily, annualised)
  • Max drawdown % (worst 20-trade losing streak)
  • Market condition matrix: test in TRENDING, RANGING, HIGH_VOL, LOW_LIQ

ROUNDS 2–N — ADVERSARIAL IMPROVEMENT
  • Do NOT repeat the same feedback — identify NEW weaknesses introduced by fixes
  • For each weakness: provide the EXACT rule change to fix it
  • Track which rules were added/removed each round
  • Re-estimate win rate only when a specific fix would genuinely improve it

PROFITABILITY GATES (all must pass):
  ✓ Win rate ≥ 60%  (scalping minimum after fees/slippage)
  ✓ Risk:Reward ≥ 1.5:1 (net of fees)
  ✓ Profit factor > 1.5
  ✓ Sharpe ratio > 1.0 (annualised)
  ✓ Max drawdown < 15%
  ✓ Clear invalidation rules for each market regime
  ✓ Position sizing defined (no more than 2% account per trade)
  ✓ Tested in at least 3 market conditions

is_profitable = true ONLY when ALL 8 gates pass.

Be ruthless. The market will be.
"""

def validate_scalping_strategy(
    strategy_description: str,
    pine_script:          Optional[str] = None,
    target_win_rate:      float         = 0.90,
    max_iterations:       int           = 5,
    print_progress:       bool          = True,
) -> list[EnterpriseScalpingValidation]:
    """
    Enterprise adversarial scalping strategy validator — Claude Opus 4.6.

    Runs up to max_iterations rounds. Each round:
    - Finds new weaknesses not caught in previous rounds
    - Tracks exact rule changes (added / removed)
    - Estimates Sharpe ratio, drawdown, profit factor, market-condition matrix
    - Stops when all 8 profitability gates pass AND win_rate ≥ target

    Parameters
    ----------
    strategy_description : plain-English strategy description
    pine_script          : optional Pine Script implementation
    target_win_rate      : stop when this win-rate estimate is reached
    max_iterations       : max adversarial rounds (default 5)
    print_progress       : print per-round progress

    Returns
    -------
    list[EnterpriseScalpingValidation]
    """
    results: list[EnterpriseScalpingValidation] = []
    history: list[dict] = []

    script_block = (
        f"\n\nPine Script Implementation:\n```pine\n{pine_script}\n```"
        if pine_script else ""
    )

    for i in range(1, max_iterations + 1):
        if print_progress:
            print(f"\n{'═'*60}", flush=True)
            print(f"  VALIDATION ROUND {i}/{max_iterations}  (target: {target_win_rate:.0%})", flush=True)
            print(f"{'═'*60}", flush=True)

        if i == 1:
            user_msg = f"""\
ENTERPRISE SCALPING STRATEGY VALIDATION — ROUND 1
Target win rate: {target_win_rate:.0%}

━━━ STRATEGY ━━━
{strategy_description}{script_block}
━━━━━━━━━━━━━━━━

REQUIRED ANALYSIS:
1. Overall win rate estimate (after 0.06% taker fees, 0.1% slippage each side)
2. Risk:reward ratio (net of all costs)
3. Sharpe ratio estimate (annualised daily returns)
4. Max drawdown % (worst realistic losing streak, 100-trade sample)
5. Profit factor (gross profit / gross loss)
6. Market condition matrix: win rate in TRENDING, RANGING, HIGH_VOL, LOW_LIQ
7. At least 5 critical weaknesses with specific fix instructions
8. All 8 profitability gates: pass/fail with reasoning
9. Verdict and next focus area"""

        else:
            prev = results[-1]
            gates_status = "✅ PROFITABLE" if prev.is_profitable else "❌ NOT PROFITABLE"
            user_msg = f"""\
VALIDATION ROUND {i} — ADVERSARIAL RE-ASSESSMENT

PREVIOUS ROUND METRICS:
  Win Rate       : {prev.overall_win_rate:.0%}  (target: {target_win_rate:.0%})
  R:R            : {prev.risk_reward_ratio:.1f}:1
  Sharpe         : {prev.sharpe_ratio_est:.2f}
  Max Drawdown   : {prev.max_drawdown_pct:.1f}%
  Profit Factor  : {prev.profit_factor:.2f}
  Status         : {gates_status}

IMPROVEMENTS APPLIED LAST ROUND:
{chr(10).join(f"  + {r}" for r in prev.improvements_made[:5]) or "  None"}

RULES ADDED: {', '.join(prev.new_rules_added[:3]) or 'None'}
RULES REMOVED: {', '.join(prev.rules_removed[:3]) or 'None'}

WEAKNESSES STILL OPEN:
{chr(10).join(f"  ⚠ {w}" for w in prev.critical_weaknesses[:5]) or "  None"}

FOCUS THIS ROUND:
{prev.next_focus}

REQUIRED:
1. Revised win-rate — did the fixes actually move the needle? By exactly how much and why?
2. Which previous weaknesses are NOW resolved? Which remain?
3. What NEW weaknesses emerged from this round's rule changes?
4. Exact new rules to add or remove (be specific: thresholds, conditions, timeframes)
5. Updated market condition matrix
6. All 8 profitability gates re-evaluated
7. Verdict: are we approaching {target_win_rate:.0%}?"""

        history.append({"role": "user", "content": user_msg})

        response = client.messages.parse(
            model         = MODEL,
            max_tokens    = 8_192,
            thinking      = {"type": "adaptive"},
            system        = _SCALPING_SYSTEM,
            messages      = history,
            output_format = EnterpriseScalpingValidation,
        )

        validation           = response.parsed_output
        validation.iteration = i
        results.append(validation)

        history.append({
            "role":    "assistant",
            "content": (
                f"Round {i}: win={validation.overall_win_rate:.0%}, "
                f"R:R={validation.risk_reward_ratio:.1f}:1, "
                f"Sharpe={validation.sharpe_ratio_est:.2f}, "
                f"DD={validation.max_drawdown_pct:.1f}%, "
                f"PF={validation.profit_factor:.2f}, "
                f"profitable={validation.is_profitable}. "
                f"Next: {validation.next_focus[:80]}"
            ),
        })

        if print_progress:
            icon = "✅" if validation.is_profitable else "❌"
            print(f"\n  {icon} Win Rate      : {validation.overall_win_rate:.0%}  (target {target_win_rate:.0%})", flush=True)
            print(f"  R:R            : {validation.risk_reward_ratio:.1f}:1", flush=True)
            print(f"  Sharpe         : {validation.sharpe_ratio_est:.2f}", flush=True)
            print(f"  Max Drawdown   : {validation.max_drawdown_pct:.1f}%", flush=True)
            print(f"  Profit Factor  : {validation.profit_factor:.2f}", flush=True)
            print(f"\n  Verdict: {validation.verdict[:120]}", flush=True)
            if validation.critical_weaknesses:
                print(f"\n  Critical Weaknesses:", flush=True)
                for w in validation.critical_weaknesses[:3]:
                    print(f"    ⚠ {w}", flush=True)
            if validation.market_conditions:
                print(f"\n  Market Condition Matrix:", flush=True)
                for mc in validation.market_conditions:
                    bar = "█" * int(mc.win_rate * 20)
                    print(f"    {mc.condition:<18} {mc.win_rate:.0%}  {bar}", flush=True)
            print(f"\n  Next focus: {validation.next_focus[:100]}", flush=True)

        if validation.overall_win_rate >= target_win_rate and validation.is_profitable:
            if print_progress:
                print(f"\n  🎯 ALL GATES PASSED — Target {target_win_rate:.0%} achieved at round {i}!", flush=True)
            break

    return results


# ═════════════════════════════════════════════════════════════════════════════
# DEMO — run with: python3 backend/claude_trading_assistant.py
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("=" * 65)
    print("  CLAUDE TRADING ASSISTANT — Enterprise Edition")
    print("  Powered by Claude Opus 4.6 (Adaptive Thinking)")
    print("=" * 65)

    # ── DEMO 1 : Enterprise Trade Decision ──────────────────────────────────
    print("\n\n📈  DEMO 1 — Enterprise Trade Decision Analysis")
    print("─" * 55)

    sample_signals = [
        {
            "Scanner":       "AMA Pro Now",
            "Signal":        "LONG",
            "Timeperiod":    "15min",
            "Angle":         "14.7°",
            "TEMA Gap":      "0.52%",
            "RSI":           "61.3",
            "Candle":        "Confirmed",
            "Daily Change":  "+2.1%",
        },
        {
            "Scanner":       "RSI CROSS UP ALMA",
            "Signal Type":   "Cross UP",
            "Timeperiod":    "1hr",
            "RSI":           "57.4",
            "RSI-ALMA":      "+2.8",
            "ALMA":          "54.6",
            "Candle Status": "Confirmed",
        },
        {
            "Scanner":       "RSI CROSS UP VWMA",
            "Signal Type":   "Cross UP",
            "Timeperiod":    "4hr",
            "RSI":           "55.1",
            "RSI-VWMA":      "+1.9",
            "Candle Status": "Confirmed",
        },
        {
            "Scanner":    "Long Conflict: SAFE",
            "Signal":     "LONG",
            "Timeperiod": "4hr",
            "Angle":      "9.2°",
        },
    ]

    decision = analyze_trade_decision(
        symbol             = "BTCUSDT.P",
        signals            = sample_signals,
        current_price      = 95_420.00,
        timeframe          = "15min",
        account_size       = 10_000.0,
        risk_per_trade_pct = 1.0,
        win_rate_estimate  = 0.64,
    )

    print(f"\n  ┌─ DECISION ──────────────────────────────")
    print(f"  │  Symbol       : {decision.symbol}")
    print(f"  │  Action       : {decision.action}")
    print(f"  │  Confidence   : {decision.confidence:.0%}")
    print(f"  │  Regime       : {decision.market_regime}")
    print(f"  │  Confluence   : {decision.confluence_score:.0%}")
    print(f"  ├─ LEVELS ───────────────────────────────")
    print(f"  │  Entry        : {decision.entry_price}")
    print(f"  │  Stop Loss    : {decision.stop_loss}")
    print(f"  │  TP1 / TP2 / TP3: {decision.take_profit_1} / {decision.take_profit_2} / {decision.take_profit_3}")
    if decision.risk_profile:
        rp = decision.risk_profile
        print(f"  ├─ RISK PROFILE ────────────────────────")
        print(f"  │  Position     : ${rp.position_size_usd:,.0f}  ({rp.position_size_pct:.1f}% account)")
        print(f"  │  Kelly Frac.  : {rp.kelly_fraction:.1%}")
        print(f"  │  Max Loss     : ${rp.max_loss_usd:,.0f}")
        print(f"  │  R:R TP1/TP2  : {rp.risk_reward_tp1:.1f} / {rp.risk_reward_tp2:.1f}")
    print(f"  ├─ CONFLUENCE FACTORS ──────────────────")
    for cf in decision.confluence_factors[:5]:
        icon = "✓" if cf.aligned else "✗"
        print(f"  │  [{icon}] {cf.name:<25} weight={cf.weight:.2f}")
    print(f"  ├─ TIMEFRAME ALIGNMENT ─────────────────")
    print(f"  │  {decision.timeframe_alignment[:70]}")
    if decision.playbook:
        print(f"  ├─ TRADE PLAYBOOK ──────────────────────")
        for step in decision.playbook.pre_entry_checklist[:3]:
            print(f"  │  ✦ {step[:65]}")
    if decision.warnings:
        print(f"  ├─ WARNINGS ───────────────────────────")
        for w in decision.warnings[:3]:
            print(f"  │  ⚠ {w[:65]}")
    print(f"  └────────────────────────────────────────")


    # ── DEMO 2 : Pine Script Builder ─────────────────────────────────────────
    print("\n\n📊  DEMO 2 — Enterprise Pine Script Builder  (up to 5 iterations)")
    print("─" * 55)

    pine_spec = """\
Build a production-grade scalping indicator:

SIGNAL LOGIC:
1. RSI(adaptive) crosses ABOVE its ALMA → LONG signal
   ALMA crosses ABOVE its own ALMA_of_ALMA → extra confirmation
2. RSI crosses BELOW its ALMA → SHORT signal
3. TEMA(RSI) direction must AGREE (rising for LONG, falling for SHORT)
4. Price must be ABOVE 20-bar VWAP for LONG, BELOW for SHORT

ADAPTIVE PARAMETERS:
• Sub-15min TF : RSI=9,  ALMA=13, TEMA=7
• 15min–1hr TF : RSI=11, ALMA=17, TEMA=9
• 4hr–1D TF    : RSI=14, ALMA=21, TEMA=11

VISUALISATION:
• Green ▲ arrow below bar on LONG, red ▼ above bar on SHORT
• Green background when LONG active, red background when SHORT active
• Info table (top-right): RSI, ALMA, TEMA, VWAP, signal state
• Plot RSI, ALMA(RSI), TEMA(RSI) in separate oscillator pane

RISK FEATURES:
• ATR-based stop-loss band plotted on chart
• alertcondition() for LONG entry, SHORT entry, and each stop-loss hit

QUALITY:
• Handle first bars (na guards everywhere)
• No repainting: signals only on confirmed (closed) candles
• Pine Script v6, no deprecated functions
"""

    pine_results = improve_pine_script(
        description    = pine_spec,
        iterations     = 5,
        print_progress = True,
    )

    final = pine_results[-1]
    print(f"\n  ┌─ PINE SCRIPT SUMMARY ──────────────────")
    print(f"  │  Iterations run   : {len(pine_results)}")
    print(f"  │  Final confidence : {final.confidence_score:.0%}")
    print(f"  │  Production ready : {final.ready_for_production}")
    print(f"  │  Compile fixes    : {sum(len(r.compile_errors_fixed) for r in pine_results)}")
    print(f"  │  Logic improve.   : {sum(len(r.logic_improvements) for r in pine_results)}")
    print(f"  └────────────────────────────────────────")

    output_path = "/tmp/enterprise_rsi_alma_indicator.pine"
    with open(output_path, "w") as fh:
        fh.write(final.script)
    print(f"\n  ✅ Script saved → {output_path}")


    # ── DEMO 3 : Enterprise Strategy Validator ───────────────────────────────
    print("\n\n🔍  DEMO 3 — Enterprise Scalping Validator  (target: 90% win rate)")
    print("─" * 55)

    strategy = """\
ENTERPRISE CRYPTO SCALPING STRATEGY — 15-MINUTE CHART

UNIVERSE: Top-20 USDT.P futures by 24h volume (min $500M)

LONG ENTRY — ALL conditions must hold:
  1. RSI(11) crosses above its ALMA on 15min chart (confirmed candle)
  2. TEMA of RSI is rising (current > previous by ≥ 0.1)
  3. Price is above 20-bar intraday VWAP
  4. 4hr candle: RSI > 50 (HTF trend filter)
  5. "Long Conflict" scanner = SAFE (no active short conflict)
  6. Volume of signal candle > 1.2× 20-bar average volume
  7. Not within 30 minutes of a scheduled macro event (FOMC, CPI, etc.)

SHORT ENTRY — mirror of above:
  1. RSI(11) crosses below ALMA (confirmed)
  2. TEMA of RSI falling
  3. Price below 20-bar VWAP
  4. 4hr RSI < 50
  5. "Short Conflict" = SAFE
  6. Volume confirmation as above

EXIT / RISK MANAGEMENT:
  Stop-loss  : 0.5% from entry (hard, market order, no exceptions)
  TP1        : +1.0% — close 50% of position
  TP2        : +2.0% — close 30% of position
  TP3        : +3.5% — close remaining 20% (trailing stop activated)
  Max risk   : 1% of account per trade (Half-Kelly)
  Max concurrent: 3 positions, same-direction trades only
  Daily loss limit: −3% account → stop trading for the day

MARKET FILTERS:
  • Skip if daily candle is a strong engulfing AGAINST trade direction
  • Skip 00:00–02:00 UTC (low liquidity)
  • Skip if 1hr ATR > 3× 20-bar average ATR (extreme volatility)
  • Skip if bid-ask spread > 0.05%
"""

    validations = validate_scalping_strategy(
        strategy_description = strategy,
        target_win_rate      = 0.90,
        max_iterations       = 5,
        print_progress       = True,
    )

    last = validations[-1]
    print(f"\n\n  ┌─ FINAL VALIDATION SUMMARY ────────────")
    print(f"  │  Rounds run       : {len(validations)}")
    print(f"  │  Final win rate   : {last.overall_win_rate:.0%}  (target {0.90:.0%})")
    print(f"  │  R:R              : {last.risk_reward_ratio:.1f}:1")
    print(f"  │  Sharpe ratio     : {last.sharpe_ratio_est:.2f}")
    print(f"  │  Max drawdown     : {last.max_drawdown_pct:.1f}%")
    print(f"  │  Profit factor    : {last.profit_factor:.2f}")
    print(f"  │  Profitable       : {'✅ YES' if last.is_profitable else '❌ NO'}")
    print(f"  ├─ ROUND-BY-ROUND ───────────────────────")
    for v in validations:
        icon = "✅" if v.is_profitable else "❌"
        print(f"  │  R{v.iteration}: {icon}  Win {v.overall_win_rate:.0%}  "
              f"R:R {v.risk_reward_ratio:.1f}  "
              f"Sharpe {v.sharpe_ratio_est:.2f}  "
              f"DD {v.max_drawdown_pct:.0f}%")
    print(f"  ├─ REMAINING WEAKNESSES ────────────────")
    for w in last.critical_weaknesses[:3]:
        print(f"  │  ⚠ {w[:65]}")
    print(f"  ├─ VERDICT ─────────────────────────────")
    print(f"  │  {last.verdict[:70]}")
    print(f"  └────────────────────────────────────────")
