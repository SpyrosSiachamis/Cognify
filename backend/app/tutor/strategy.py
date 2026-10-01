"""choose_strategy: the teaching method from the student's observed history (code, not AI).

Rules (docs/ARCHITECTURE.md): no history for this gap type -> the default method
(cold_start); otherwise the best score (independent successes + 1) / (uses + 2),
ties to more uses (best_known). A forced experiment picks a method never used for
this gap, else the least used one. The other exploration rules (F12: about one
session in five, expiry, never twice in a row) are not built yet.
"""

from uuid import UUID

from app.common.vocab import GapType, Strategy, values
from app.history import HistoryStore
from app.history.schema import StrategyStat, now

from .schema import ChooseStrategyResult, EvidenceCounts

# Defaults use the four P0 methods (SPEC F10).
DEFAULT_METHOD: dict[GapType, Strategy] = {
    "recognition": "visual_decomposition",
    "representation": "visual_decomposition",
    "concept": "socratic",
    "procedure": "worked_example",
    "strategy_choice": "socratic",
    "self_correction": "micro_hint",
    "transfer": "socratic",
}
P0_METHODS: tuple[Strategy, ...] = ("socratic", "visual_decomposition", "worked_example", "micro_hint")


def _score(stat: StrategyStat) -> tuple[float, int]:
    return ((stat.independent_successes + 1) / (stat.uses + 2), stat.uses)


def _days_since(stat: StrategyStat | None) -> int | None:
    if stat is None or stat.last_success_at is None:
        return None
    return max(0, (now() - stat.last_success_at).days)


def _counts(stat: StrategyStat | None) -> EvidenceCounts:
    if stat is None:
        return EvidenceCounts(uses=0, independent_successes=0)
    return EvidenceCounts(uses=stat.uses, independent_successes=stat.independent_successes)


def choose_strategy(
    store: HistoryStore, student_id: UUID, gap: GapType, force_experiment: bool = False
) -> ChooseStrategyResult:
    stats = {s.method: s for s in store.strategy_stats(student_id, gap)}

    if force_experiment:
        untried = [m for m in P0_METHODS + values(Strategy) if m not in stats]
        if untried:
            method, stat = untried[0], None
        else:
            stat = min(stats.values(), key=lambda s: (s.uses, s.method))
            method = stat.method
        return ChooseStrategyResult(
            method=method,
            mode="experiment",
            reason=f"Trying something different this time: {method.replace('_', ' ')} "
            f"({'never tried' if stat is None else f'tried {stat.uses} times'} for you on {gap} gaps).",
            evidence=_counts(stat),
            last_success_days_ago=_days_since(stat),
        )

    if not stats:
        method = DEFAULT_METHOD[gap]
        return ChooseStrategyResult(
            method=method,
            mode="cold_start",
            reason=f"No history yet for {gap} gaps, so starting with {method.replace('_', ' ')}.",
            evidence=_counts(None),
        )

    best = max(stats.values(), key=_score)
    return ChooseStrategyResult(
        method=best.method,
        mode="best_known",
        reason=f"Worked {best.independent_successes} of {best.uses} times for you on {gap} gaps.",
        evidence=_counts(best),
        last_success_days_ago=_days_since(best),
    )
