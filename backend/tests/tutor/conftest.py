"""A seeded store and a teach request builder for Maria and the ball problem."""

import pytest

from app.history import InMemoryHistory
from app.seed import seed_store
from app.seed.data import MARIA_ID
from app.session.schema import Solution
from app.user.ports import TeachRequest

PROBLEM = "A ball is thrown upward at 20 m/s. How high does it go? (Use g = 9.8 m/s^2)"
SOLUTION = Solution(
    result="20.4 m",
    steps=["At the highest point v = 0.", "Use v^2 = u^2 - 2gh.", "h = 400 / 19.6 = 20.4 m."],
)
MARIA_FIRST_THOUGHT = "I found the time to the top, about 2.04 s, but I don't know how to get the height from the time."


@pytest.fixture
def store() -> InMemoryHistory:
    fresh = InMemoryHistory()
    seed_store(fresh)
    return fresh


def teach_request(text: str = MARIA_FIRST_THOUGHT, **update) -> TeachRequest:
    fields = dict(
        student_id=MARIA_ID, problem=PROBLEM, concept_name="Constant-acceleration kinematics", solution=SOLUTION,
        student_text=text, first_thought=True, hints_used=0, teach_turns=1, force_experiment=False,
        after_not_yet=False,
    )
    return TeachRequest(**(fields | update))
