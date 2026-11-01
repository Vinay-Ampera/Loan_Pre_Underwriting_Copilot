"""The precedent bonus, in code. The Policy agent only finds matches; this turns them into points.

Only an approved precedent whose final decision was "approve" can lift a case, and only by the
rules-file cap. `score_case` still refuses the bonus unless the case is in the refer band with no
hard-rule stop and no cap-to-refer rule failing, so a precedent can never override a hard rule.
"""

from collections.abc import Iterable

from app.rag.schemas import PrecedentMatch
from app.scoring.rules import RuleSet


def precedent_bonus(
    matches: Iterable[PrecedentMatch], ruleset: RuleSet
) -> tuple[float, str | None]:
    """(bonus points, id of the precedent that earned them). (0.0, None) when nothing qualifies."""
    usable = [
        m for m in matches
        if m.final_decision == "approve" and m.similarity >= ruleset.precedent.similarity_min
    ]  # fmt: skip
    if not usable:
        return 0.0, None
    best = max(usable, key=lambda m: m.similarity)
    return round(
        min(ruleset.precedent.bonus_max, ruleset.precedent.bonus_max * best.similarity), 2
    ), best.id
