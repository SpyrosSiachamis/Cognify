"""Cross-domain generalization cases: what the tutor must tell apart, outside the seeded physics problem.

Each case is a problem and a student's answer, plus the expectations a person wrote down beforehand.
Only `problem` and `student` reach the tutor; every other field stays in the test.

Patterns:
- incomplete: valid reasoning so far that stops before the answer. Unfinished is not wrong.
- incorrect: a false claim, invalid inference, wrong calculation or misconception. The error must be found.
- right_answer_wrong_reasoning: the final answer is right, but the stated reason is false. The reasoning
  is judged, not the answer.

`evidence` is a short piece of the student's own text that the relevant step should quote: the correct
work (incomplete) or the false claim (the other two patterns). It is matched ignoring case and spaces.
"""

from dataclasses import dataclass
from typing import Literal

Pattern = Literal["incomplete", "incorrect", "right_answer_wrong_reasoning"]


@dataclass(frozen=True)
class CrossDomainCase:
    case_id: str
    domain: str
    pattern: Pattern
    problem: str
    student: str
    demonstrated: str  # what the student has shown
    missing: str  # what is still to do or to understand
    error: str | None  # the misconception or error, if any
    expected_diagnosis: str  # in words: what a correct diagnosis says
    evidence: str  # the piece of the student's text the relevant step should quote
    expected_behaviour: str


CASES = [
    # ---- Mathematics ----
    CrossDomainCase(
        "math_incomplete_factoring", "Mathematics", "incomplete",
        "Solve x^2 - 5x + 6 = 0.",
        "I factored it as (x - 2)(x - 3) = 0, but I'm not sure what that tells me about x.",
        demonstrated="correct factoring of the quadratic",
        missing="using the zero-product property to get x = 2 or x = 3",
        error=None,
        expected_diagnosis="factoring correct; the step from the factored form to the solutions is missing",
        evidence="(x - 2)(x - 3)",
        expected_behaviour="credits the factoring, no step wrong, teaches toward the next step",
    ),
    CrossDomainCase(
        "math_incorrect_percent", "Mathematics", "incorrect",
        "What is 15% of 80?",
        "15% means divide by 15, so 80 / 15 = 5.33.",
        demonstrated="knows a percentage calls for an operation on 80",
        missing="15% means 15/100, so 0.15 x 80 = 12",
        error="reads 'percent' as dividing by the percentage number",
        expected_diagnosis="wrong step: dividing by 15 instead of multiplying by 15/100",
        evidence="80 / 15",
        expected_behaviour="marks the division wrong with a stated error",
    ),
    CrossDomainCase(
        "math_right_answer_prime_rule", "Mathematics", "right_answer_wrong_reasoning",
        "Is 91 a prime number? Explain.",
        "No, 91 is not prime because every number ending in 1 is divisible by 7.",
        demonstrated="the right conclusion (91 = 7 x 13 is not prime)",
        missing="a valid reason: finding an actual factor of 91",
        error="a false rule: numbers ending in 1 are not all divisible by 7 (11, 31 are not)",
        expected_diagnosis="the conclusion is right but the stated rule is false",
        evidence="ending in 1 is divisible by 7",
        expected_behaviour="does not accept the answer as understanding; marks the reasoning wrong",
    ),
    # ---- Physics ----
    CrossDomainCase(
        "physics_incomplete_energy", "Physics", "incomplete",
        "A 1200 W kettle runs for 5 minutes. How much energy does it use, in joules?",
        "Energy is power times time, and 5 minutes is 300 seconds, but I don't know how to finish.",
        demonstrated="the relation E = P t and the conversion to 300 s",
        missing="multiplying 1200 W by 300 s (360000 J)",
        error=None,
        expected_diagnosis="relation and unit conversion correct; the final multiplication is missing",
        evidence="300 seconds",
        expected_behaviour="credits the relation and the conversion, no step wrong",
    ),
    CrossDomainCase(
        "physics_incorrect_falling", "Physics", "incorrect",
        "A feather and a hammer are dropped together on the Moon, where there is no air. Which lands first?",
        "The hammer lands first because heavier objects fall faster.",
        demonstrated="an attempt to compare the two objects",
        missing="without air resistance all objects fall with the same acceleration, so they land together",
        error="believes heavier objects fall faster",
        expected_diagnosis="a misconception about free fall",
        evidence="heavier objects fall faster",
        expected_behaviour="marks the claim wrong and names the misconception",
    ),
    CrossDomainCase(
        "physics_right_answer_no_weight", "Physics", "right_answer_wrong_reasoning",
        "A 5 kg box rests on a table. What is the net force on it?",
        "The net force is 0 N because the box has no weight while it sits on the table.",
        demonstrated="the right value (0 N)",
        missing="weight and the table's normal force are equal and opposite, so they cancel",
        error="believes the box has no weight on the table",
        expected_diagnosis="the answer is right but the reason (no weight) is false",
        evidence="has no weight",
        expected_behaviour="marks the reasoning wrong although the answer is right",
    ),
    # ---- Biology ----
    CrossDomainCase(
        "biology_incomplete_breathing", "Biology", "incomplete",
        "Explain why a person's breathing rate increases during exercise.",
        "During exercise the muscles do more respiration, so they produce more carbon dioxide. "
        "I'm not sure how that connects to breathing faster.",
        demonstrated="more respiration in the muscles produces more carbon dioxide",
        missing="the body detects the higher carbon dioxide and raises the breathing rate to remove it",
        error=None,
        expected_diagnosis="the first link of the mechanism is right; the link to breathing is missing",
        evidence="produce more carbon dioxide",
        expected_behaviour="credits the first link, no step wrong",
    ),
    CrossDomainCase(
        "biology_incorrect_plant_mass", "Biology", "incorrect",
        "Where do plants get most of the mass they build as they grow?",
        "Plants get most of their mass from the soil, because their roots take up nutrients.",
        demonstrated="knows roots take up nutrients",
        missing="most of the mass comes from carbon dioxide in the air, fixed by photosynthesis",
        error="believes most plant mass comes from the soil",
        expected_diagnosis="a misconception about where plant mass comes from",
        evidence="from the soil",
        expected_behaviour="marks the claim wrong and names the misconception",
    ),
    CrossDomainCase(
        "biology_right_answer_eye_colour", "Biology", "right_answer_wrong_reasoning",
        "Can two parents with brown eyes have a child with blue eyes? Explain.",
        "Yes, because a child's eye colour is chosen randomly and doesn't depend on the parents.",
        demonstrated="the right answer (yes)",
        missing="both parents can carry a recessive blue allele and each pass it on",
        error="believes inheritance does not depend on the parents",
        expected_diagnosis="the answer is right but the explanation is false",
        evidence="doesn't depend on the parents",
        expected_behaviour="marks the explanation wrong although the answer is right",
    ),
    # ---- History ----
    CrossDomainCase(
        "history_incomplete_printing", "History", "incomplete",
        "Could the printing press (invented around 1440) have helped spread Martin Luther's 95 Theses (1517)? "
        "Explain using the dates.",
        "The printing press was invented around 1440, which is before 1517. I'm not sure how to use that to answer.",
        demonstrated="the correct order of the two dates",
        missing="linking the press's availability to copying and spreading the Theses quickly",
        error=None,
        expected_diagnosis="chronology correct; the causal link to the spread is missing",
        evidence="before 1517",
        expected_behaviour="credits the chronology, no step wrong",
    ),
    CrossDomainCase(
        "history_incorrect_telegraph", "History", "incorrect",
        "Could Napoleon have used the electric telegraph to command his army at the Battle of Waterloo in 1815?",
        "Yes, because the electric telegraph was already in common use by 1800.",
        demonstrated="an attempt to reason from dates",
        missing="the electric telegraph came into practical use only in the 1830s and 1840s",
        error="a false chronological claim about the telegraph",
        expected_diagnosis="the date claim is false, so the conclusion does not follow",
        evidence="common use by 1800",
        expected_behaviour="marks the date claim wrong",
    ),
    CrossDomainCase(
        "history_right_answer_older_country", "History", "right_answer_wrong_reasoning",
        "Which came first, the American Declaration of Independence or the French Revolution? Explain.",
        "The Declaration of Independence came first, because the United States is an older country than France.",
        demonstrated="the right order (1776 before 1789)",
        missing="a reason based on the actual dates of the two events",
        error="a false claim: the United States is not older than France",
        expected_diagnosis="the order is right but the reason is false",
        evidence="older country than France",
        expected_behaviour="marks the reasoning wrong although the order is right",
    ),
    # ---- Programming ----
    CrossDomainCase(
        "programming_incomplete_average", "Programming", "incomplete",
        "What does f([3, 7, 2]) return?\n\ndef f(xs):\n    total = 0\n    for x in xs:\n        total += x\n"
        "    return total / len(xs)",
        "The loop adds the numbers, so total becomes 12 after the loop. I'm not sure what the last line does.",
        demonstrated="tracing the loop correctly to total = 12",
        missing="dividing by len(xs) = 3 to return 4.0",
        error=None,
        expected_diagnosis="the loop trace is correct; the return expression is not evaluated",
        evidence="total becomes 12",
        expected_behaviour="credits the trace, no step wrong",
    ),
    CrossDomainCase(
        "programming_incorrect_range", "Programming", "incorrect",
        "What does this Python code print?\n\nfor i in range(3):\n    print(i)",
        "It prints 1, 2, 3 because range(3) counts from 1 up to 3.",
        demonstrated="knows the loop prints one value per iteration",
        missing="range(3) gives 0, 1, 2: it starts at 0 and stops before 3",
        error="believes range(n) counts from 1 to n",
        expected_diagnosis="a misconception about range's start and end",
        evidence="counts from 1 up to 3",
        expected_behaviour="marks the claim about range wrong",
    ),
    CrossDomainCase(
        "programming_right_answer_modulo", "Programming", "right_answer_wrong_reasoning",
        "With x = 7, what does print(x % 2 == 1) print? Explain.",
        "It prints True, because % divides x by 2 and 7 / 2 = 3.5, which isn't a whole number.",
        demonstrated="the right output (True)",
        missing="% gives the remainder: 7 % 2 = 1, so the comparison is True",
        error="believes % is division",
        expected_diagnosis="the output is right but the meaning of % is wrong",
        evidence="% divides x by 2",
        expected_behaviour="marks the explanation of % wrong although the output is right",
    ),
    # ---- Chemistry ----
    CrossDomainCase(
        "chemistry_incomplete_moles", "Chemistry", "incomplete",
        "How many moles are in 36 g of water (H2O)?",
        "The molar mass of water is 2(1) + 16 = 18 g/mol. I don't know what to do with that.",
        demonstrated="the correct molar mass, 18 g/mol",
        missing="moles = mass / molar mass = 36 / 18 = 2 mol",
        error=None,
        expected_diagnosis="molar mass correct; the division to get moles is missing",
        evidence="18 g/mol",
        expected_behaviour="credits the molar mass, no step wrong",
    ),
    CrossDomainCase(
        "chemistry_incorrect_dissolving", "Chemistry", "incorrect",
        "When salt dissolves in water, does the salt disappear? Explain.",
        "Yes, the salt is destroyed when it dissolves, so it is no longer there.",
        demonstrated="notices the salt can no longer be seen",
        missing="the salt separates into ions spread through the water; its mass is conserved",
        error="believes dissolving destroys the substance",
        expected_diagnosis="a misconception about dissolving and conservation of mass",
        evidence="salt is destroyed",
        expected_behaviour="marks the claim wrong and names the misconception",
    ),
    CrossDomainCase(
        "chemistry_right_answer_ice", "Chemistry", "right_answer_wrong_reasoning",
        "Does ice float on liquid water? Explain why.",
        "Yes, because ice is a solid and solids are always lighter than liquids.",
        demonstrated="the right answer (ice floats)",
        missing="ice is less dense than water because hydrogen bonds hold its molecules in an open structure",
        error="a false generalization: most solids are denser than their liquids",
        expected_diagnosis="the answer is right but the general rule given is false",
        evidence="solids are always lighter than liquids",
        expected_behaviour="marks the reasoning wrong although the answer is right",
    ),
    # ---- Logic / critical reasoning ----
    CrossDomainCase(
        "logic_incomplete_syllogism", "Logic / critical reasoning", "incomplete",
        "Premises: All mammals are warm-blooded. All whales are mammals. Some sea creatures are whales. "
        "What can you conclude about some sea creatures?",
        "From the first two premises, all whales are warm-blooded. I'm not sure how the third premise fits in.",
        demonstrated="a valid inference from the first two premises",
        missing="combining it with the third premise: some sea creatures are warm-blooded",
        error=None,
        expected_diagnosis="the first inference is valid; the final inference is missing",
        evidence="all whales are warm-blooded",
        expected_behaviour="credits the first inference, no step wrong",
    ),
    CrossDomainCase(
        "logic_incorrect_converse", "Logic / critical reasoning", "incorrect",
        "If it rains, the street gets wet. The street is wet. Does it follow that it rained?",
        "Yes, it must have rained, because the street is wet and rain makes the street wet.",
        demonstrated="restates the premises correctly",
        missing="the street could be wet for another reason; the conclusion does not follow",
        error="affirming the consequent (an invalid inference)",
        expected_diagnosis="an invalid inference: affirming the consequent",
        evidence="it must have rained",
        expected_behaviour="marks the inference wrong",
    ),
    CrossDomainCase(
        "logic_right_answer_even", "Logic / critical reasoning", "right_answer_wrong_reasoning",
        "If a number is divisible by 4, then it is even. 10 is even. Is 10 divisible by 4? Explain.",
        "No. 10 is not divisible by 4, because it is even, and even numbers are not divisible by 4.",
        demonstrated="the right answer (no)",
        missing="the premise says nothing about even numbers in general; check 10 / 4 directly",
        error="a false claim: many even numbers (4, 8, 12) are divisible by 4",
        expected_diagnosis="the answer is right but the stated rule is false",
        evidence="even numbers are not divisible by 4",
        expected_behaviour="marks the reasoning wrong although the answer is right",
    ),
]
