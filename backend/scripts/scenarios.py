"""Premade demo data: the ball problem and the scripted Maria story."""

from app.seed.data import MARIA_ID, NIKOS_ID

STUDENTS = {"maria": MARIA_ID, "nikos": NIKOS_ID}

BALL_PROBLEM = (
    "A ball is thrown vertically upward with an initial velocity of 20 m/s. "
    "How high does it go before it starts to fall? (Use g = 9.8 m/s^2)"
)

# The Maria story (SPEC.md section 5): she finds the time, then stops; then the
# stress test (stub follow-up) and her independent answer to it.
MARIA_TURNS = [
    "I found the time to the top, about 2.04 s, but I do not know how to get the height from the time.",
    "At the top the speed is 0. I know u = 20 m/s, v = 0 and g = 9.8, and I want the height h.",
    "So I do not need the time at all? I could use v^2 = u^2 - 2gh with v = 0 and solve for h.",
    "v^2 = u^2 - 2gh with v = 0 and u = 15: h = 225 / 19.6, about 11.5 m above the balcony.",
]
