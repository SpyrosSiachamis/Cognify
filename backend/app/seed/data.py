"""The seeded demo history: one source of truth (docs/DATA.md).

Every row has is_seeded=True. Dates are relative to "now" so the rule
"a success older than about 30 days expires" behaves the same every day.
"""

import random
from datetime import datetime, timedelta
from uuid import UUID

from app.common.vocab import GapType, Strategy
from app.services.history.schema import (
    Concept,
    ConceptState,
    Outcome,
    Record,
    Student,
    now as current_time,
)

MARIA_ID = UUID("16e82ef2-adee-4671-8393-c6b50ac91672")
NIKOS_ID = UUID("00915798-79f9-4362-84d0-839a0b3df9f2")
KINEMATICS_ID = UUID("44d54897-9ec4-45b9-8da1-d4ea95697d1d")

SEED_LABEL = "Seeded demo history"

# (student, gap, method, uses, independent successes, days ago of first use, days ago of last use)
HISTORY: list[tuple[UUID, GapType, Strategy, int, int, int, int]] = [
    (MARIA_ID, "recognition", "visual_decomposition", 9, 7, 40, 6),
    (MARIA_ID, "recognition", "worked_example", 7, 4, 35, 12),
    (MARIA_ID, "recognition", "socratic", 5, 3, 28, 20),
    # analogy and counterexample: never used
    (NIKOS_ID, "procedure", "worked_example", 6, 5, 38, 4),
    (NIKOS_ID, "procedure", "visual_decomposition", 4, 2, 30, 9),
    (NIKOS_ID, "procedure", "socratic", 3, 1, 25, 15),
]


class Seed(Record):
    students: list[Student]
    concepts: list[Concept]
    outcomes: list[Outcome]
    concept_states: list[ConceptState]


def _fixed_id(*parts: object) -> UUID:
    """A repeatable UUID v4, so loading the seed twice never makes duplicate rows."""
    return UUID(int=random.Random("-".join(map(str, parts))).getrandbits(128), version=4)


def _outcome_rows(
    student_id: UUID,
    gap: GapType,
    method: Strategy,
    uses: int,
    successes: int,
    first_days: int,
    last_days: int,
    now: datetime,
) -> list[Outcome]:
    rows = []
    for i in range(uses):
        # Row i succeeds when the running success total ticks up, so successes are
        # spread evenly and the most recent row is always a success.
        success = (i + 1) * successes // uses > i * successes // uses
        step = (first_days - last_days) / (uses - 1) if uses > 1 else 0
        days_ago = round(first_days - i * step)
        rows.append(
            Outcome(
                id=_fixed_id(student_id, gap, method, i),
                student_id=student_id,
                session_id=None,
                concept_id=KINEMATICS_ID,
                gap_type=gap,
                method=method,
                decision_mode="best_known",
                result="VERIFIED" if success else "NOT YET",
                independent=success,
                hints_used=i % 2 if success else 2 + i % 2,
                concept_before="weak",
                concept_after="fragile" if success else "weak",
                evidence=f"{SEED_LABEL}: earlier session {i + 1} on a {gap} gap.",
                is_seeded=True,
                created_at=now - timedelta(days=days_ago),
            )
        )
    return rows


def build_seed(now: datetime | None = None) -> Seed:
    now = now or current_time()
    outcomes = [
        row for spec in HISTORY for row in _outcome_rows(*spec, now=now)
    ]
    return Seed(
        students=[
            Student(id=MARIA_ID, display_name="Maria", is_seeded=True, created_at=now),
            Student(id=NIKOS_ID, display_name="Nikos", is_seeded=True, created_at=now),
        ],
        concepts=[Concept(id=KINEMATICS_ID, name="Constant-acceleration kinematics")],
        outcomes=outcomes,
        concept_states=[
            ConceptState(
                student_id=MARIA_ID,
                concept_id=KINEMATICS_ID,
                state="fragile",
                evidence=[f"{SEED_LABEL}: recognition gap in 3 earlier sessions."],
                is_seeded=True,
                updated_at=now,
            ),
            ConceptState(
                student_id=NIKOS_ID,
                concept_id=KINEMATICS_ID,
                state="fragile",
                evidence=[f"{SEED_LABEL}: procedure gap in 3 earlier sessions."],
                is_seeded=True,
                updated_at=now,
            ),
        ],
    )
