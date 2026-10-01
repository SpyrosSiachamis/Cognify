"""Cross-domain evaluation v2: 7 domains x 10 reasoning patterns = 70 hand-written cases.

Only `problem` and `student` reach the tutor (plus, for repair follow-ups, the previous turn's diagnosis as the
session would pass it). Everything else is the expectation, written before any model run.

Patterns (one per domain each):
- incomplete_early_stop: correct start, stops before the end. Unfinished is not wrong.
- incomplete_implicit_step: a valid jump that leaves out an inference the problem explicitly asks for.
- incorrect_conceptual: a false conceptual claim (the gap is conceptual).
- incorrect_local_error: valid reasoning with one local slip (the gap is not conceptual).
- correct_answer_wrong_reasoning: right answer, false or invalid justification.
- correct_reasoning_wrong_answer: sound reasoning, wrong final value from a local slip.
- correct_work: valid and complete (sometimes a longer route, sometimes stated with doubt). No gap.
- no_reasoning: a bare answer. No label without evidence.
- misconception: a systematic wrong belief, distinct from the domain's local slip.
- repair_followup: a follow-up after a taught gap: genuine, partial or false repair.

Traps:
A correct answer + invalid reasoning, B wrong answer + mostly valid reasoning, C correct reasoning + wrong final
transcription, D lucky guess, E confidence trap, F uncertainty trap, G partial repair, H false repair,
I several valid steps then one wrong step, J evidence localization (valid work and an unresolved gap in separate
sentences that must not be merged into one step).

Quotes are matched ignoring case and spaces. Step roles are never part of a check.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.tutor.schema import PriorDiagnosis, Step

Pattern = Literal[
    "incomplete_early_stop", "incomplete_implicit_step", "incorrect_conceptual", "incorrect_local_error",
    "correct_answer_wrong_reasoning", "correct_reasoning_wrong_answer", "correct_work", "no_reasoning",
    "misconception", "repair_followup",
]
PATTERNS: tuple[str, ...] = Pattern.__args__  # type: ignore[attr-defined]
RepairKind = Literal["genuine", "partial", "false"]
DOMAINS = ("Mathematics", "Physics", "Biology", "History", "Programming", "Chemistry", "Logic / critical reasoning")


@dataclass(frozen=True)
class Expect:
    """What the turn must show. Each True field is one required check; None means not tested."""

    credit_required: bool = False  # a correct step quotes credit_quote
    wrong_required: bool = False  # a wrong step quotes error_quote
    no_wrong: bool = False  # no step is marked wrong
    error_required: bool = False  # an error analysis is stated
    no_error: bool = False  # no error analysis is stated
    gap_required: bool = False  # a main gap is named
    no_gap: bool = False  # no main gap is named
    gap_concept: bool | None = None  # True: the gap is concept; False: a gap is named and it is not concept
    missing_required: bool = False  # some step is still missing
    no_missing: bool = False  # no step is missing
    modes: frozenset[str] = frozenset({"teach"})  # allowed turn modes
    repaired: bool | None = None  # the repair check's result, for follow-ups
    reply_approved: bool = False  # the verifier approved a teaching draft (no safe fallback)


TEACH = frozenset({"teach"})


def expect_for(pattern: str, repair: RepairKind | None = None) -> Expect:
    """The expected behaviour of each pattern, written out explicitly (see the matrix in the docs)."""
    match pattern:
        case "incomplete_early_stop":
            return Expect(credit_required=True, no_wrong=True, no_error=True, missing_required=True,
                          gap_required=True, gap_concept=False, modes=TEACH, reply_approved=True)
        case "incomplete_implicit_step":
            return Expect(credit_required=True, no_wrong=True, no_error=True, gap_required=True, gap_concept=False,
                          modes=TEACH, reply_approved=True)
        case "incorrect_conceptual" | "misconception":
            return Expect(wrong_required=True, error_required=True, gap_required=True, gap_concept=True,
                          modes=TEACH, reply_approved=True)
        case "incorrect_local_error" | "correct_reasoning_wrong_answer":
            return Expect(credit_required=True, wrong_required=True, error_required=True, gap_required=True,
                          gap_concept=False, modes=TEACH, reply_approved=True)
        case "correct_answer_wrong_reasoning":
            return Expect(wrong_required=True, error_required=True, gap_required=True, modes=TEACH,
                          reply_approved=True)
        case "correct_work":
            return Expect(no_wrong=True, no_missing=True, no_gap=True, modes=frozenset({"acknowledge"}))
        case "no_reasoning":
            # Either withholding move is acceptable: a probe, or moving on to the independent stress test.
            return Expect(no_wrong=True, no_error=True, no_gap=True, modes=frozenset({"probe", "acknowledge"}))
        case "repair_followup" if repair == "genuine":
            return Expect(credit_required=True, repaired=True, modes=frozenset({"acknowledge"}))
        case "repair_followup" if repair == "partial":
            # The fixed part is credited, the part still wrong is flagged, and the gap is not counted as repaired.
            return Expect(credit_required=True, wrong_required=True, repaired=False, modes=TEACH, reply_approved=True)
        case "repair_followup" if repair == "false":
            return Expect(wrong_required=True, repaired=False, modes=TEACH, reply_approved=True)
    raise ValueError(f"no expectation for {pattern} / {repair}")


@dataclass(frozen=True)
class CrossDomainCaseV2:
    case_id: str
    domain: str
    pattern: str
    traps: tuple[str, ...]
    problem: str
    student: str
    demonstrated: str
    missing: str
    error: str | None
    expected_diagnosis: str
    rationale: str
    trap_description: str
    credit_quote: str | None = None  # valid work that must be credited
    error_quote: str | None = None  # the false or slipped claim that must be marked wrong
    leak_forms: tuple[str, ...] = ()  # answer strings the reply must not contain
    repair: RepairKind | None = None
    previous_attempt: str | None = None  # the student's earlier message (repair follow-ups; not sent)
    prior: PriorDiagnosis | None = None  # the earlier turn's diagnosis, as the session passes it
    expect: Expect = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "expect", expect_for(self.pattern, self.repair))


def prior(gap: str, role: str, status: str, quote: str) -> PriorDiagnosis:
    return PriorDiagnosis(steps=[Step(role=role, status=status, quote=quote)], main_gap=gap)


C = CrossDomainCaseV2

CASES: list[CrossDomainCaseV2] = [
    # ======================= Mathematics =======================
    C("math_early_stop_phone_plan", "Mathematics", "incomplete_early_stop", ("J",),
      "A phone plan costs 15 euros per month plus 2 euros per GB of data. One month's bill was 31 euros. "
      "How many GB were used?",
      "The data part of the bill is 31 - 15 = 16 euros. I don't know how to go from euros to GB.",
      demonstrated="separates the fixed fee: the data cost is 16 euros",
      missing="dividing the data cost by the price per GB",
      error=None,
      expected_diagnosis="the subtraction is correct; the division by the per-GB price is not done yet",
      rationale="Word-problem setup: the first operation is right and is stated on its own; the student then says "
                "they cannot continue. Nothing written is false.",
      trap_description="J: the valid sentence and the stuck sentence are separate and must not be merged.",
      credit_quote="31 - 15 = 16", leak_forms=("8 GB", "= 8")),
    C("math_implicit_only_solution", "Mathematics", "incomplete_implicit_step", (),
      "Explain why x = 2 is the only solution of 3x + 4 = 10. Give the reasoning, not just the value.",
      "x = 2 because 3(2) + 4 = 10.",
      demonstrated="checks that x = 2 satisfies the equation",
      missing="why no other value works (solving the equation step by step gives one value)",
      error=None,
      expected_diagnosis="the check is correct but it does not show uniqueness, which the question asks for",
      rationale="Substitution shows x = 2 works, not that it is the only solution; the question explicitly asks "
                "for the only-solution reasoning, so a necessary inference is missing, yet nothing is false.",
      trap_description="A valid fact that answers half of the question: easy to accept as complete.",
      credit_quote="3(2) + 4 = 10"),
    C("math_conceptual_square_of_sum", "Mathematics", "incorrect_conceptual", ("E",),
      "Simplify (x + 3)^2.",
      "I'm completely sure: (x + 3)^2 = x^2 + 9, because you square each term.",
      demonstrated="knows squaring is involved",
      missing="(x + 3)^2 = (x + 3)(x + 3) = x^2 + 6x + 9",
      error="believes the square of a sum is the sum of the squares",
      expected_diagnosis="a conceptual error about squaring a sum",
      rationale="Squaring each term is a general wrong rule, not a slip in one calculation.",
      trap_description="E: stated with certainty; confidence must not stand in for correctness.",
      error_quote="x^2 + 9", leak_forms=("6x", "x^2 + 6x")),
    C("math_local_error_linear", "Mathematics", "incorrect_local_error", ("B", "I"),
      "Solve 4(x - 2) = 3x + 5.",
      "Expand: 4x - 8 = 3x + 5. Subtract 3x from both sides: x - 8 = 5. Add 8: x = 12.",
      demonstrated="correct expansion and correct collection of x terms",
      missing="5 + 8 = 13",
      error="an addition slip in the last step",
      expected_diagnosis="procedure is sound; one arithmetic slip at the end",
      rationale="Every algebraic move is right; only 5 + 8 was added wrongly. That is local, not conceptual.",
      trap_description="B and I: several valid steps then one slip; it must not become a misconception.",
      credit_quote="4x - 8 = 3x + 5", error_quote="x = 12", leak_forms=("x = 13", "= 13")),
    C("math_right_answer_cancel_sixes", "Mathematics", "correct_answer_wrong_reasoning", ("A",),
      "Simplify the fraction 16/64.",
      "Cancel the 6s: 16/64 = 1/4.",
      demonstrated="the right value, 1/4",
      missing="a valid reason: divide top and bottom by 16",
      error="cancels digits, which is not a valid operation on fractions",
      expected_diagnosis="the answer is right by accident; the cancelling of digits is invalid",
      rationale="Cancelling digits only happens to give the right value here (it fails for 12/24); the method is "
                "invalid even though the result is right.",
      trap_description="A: a right answer reached by an invalid route.",
      error_quote="Cancel the 6s"),
    C("math_right_reasoning_wrong_price", "Mathematics", "correct_reasoning_wrong_answer", ("C",),
      "A shirt costs 40 euros and is reduced by 25%. What is the new price?",
      "25% of 40 is 0.25 × 40 = 10, so the new price is 40 - 10 = 20 euros.",
      demonstrated="computes the discount correctly and knows to subtract it",
      missing="40 - 10 = 30",
      error="a subtraction slip in the final value",
      expected_diagnosis="the method is correct; the final subtraction is wrong",
      rationale="Percent and discount reasoning are right; only the last subtraction is wrong.",
      trap_description="C: understanding shown, wrong final value; not a misconception.",
      credit_quote="0.25 × 40 = 10", error_quote="40 - 10 = 20", leak_forms=("30 euros", "= 30")),
    C("math_correct_trial_pairs", "Mathematics", "correct_work", (),
      "Find two consecutive whole numbers whose sum is 37.",
      "I tried pairs: 17 + 18 = 35, 18 + 19 = 37. So the numbers are 18 and 19.",
      demonstrated="a systematic trial that reaches and checks the answer",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete; a longer route than algebra is still correct",
      rationale="Trial and checking is a valid method and the answer is verified in the student's own work.",
      trap_description="Valid but not the textbook method: no gap may be invented."),
    C("math_bare_percent", "Mathematics", "no_reasoning", ("D",),
      "What is 15% of 60?",
      "9.",
      demonstrated="a value only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare number cannot show understanding or a gap; labelling a gap would be guessing.",
      trap_description="D: a correct bare answer, which could be a guess."),
    C("math_misconception_multiplying", "Mathematics", "misconception", (),
      "Which is larger, 8 ÷ 0.5 or 8 × 0.5? Explain.",
      "8 × 0.5 is larger, because multiplying always makes a number bigger and dividing always makes it smaller, "
      "so 8 ÷ 0.5 = 4.",
      demonstrated="knows both operations apply to 8",
      missing="dividing by a number below 1 makes the result larger: 8 ÷ 0.5 = 16",
      error="believes multiplying always increases and dividing always decreases",
      expected_diagnosis="a systematic misconception about multiplying and dividing by numbers below 1",
      rationale="The wrong value comes from a general belief the student states, unlike the local slip in the "
                "linear-equation case.",
      trap_description="A deep belief that must be named as conceptual, not as an arithmetic slip.",
      error_quote="multiplying always makes a number bigger", leak_forms=("= 16", "is 16")),
    C("math_repair_genuine_linear", "Mathematics", "repair_followup", (),
      "Solve 2x + 6 = 14.",
      "Subtract 6 from both sides: 2x = 14 - 6 = 8, so x = 4.",
      demonstrated="moves the constant correctly this time and finishes",
      missing="nothing",
      error=None,
      expected_diagnosis="the earlier procedural gap is repaired with new work",
      rationale="Earlier the student added 6 instead of subtracting it; now the step is done correctly in new "
                "words and the solution is complete.",
      trap_description="A genuine repair must be recognised and not retaught.",
      credit_quote="2x = 14 - 6 = 8", repair="genuine",
      previous_attempt="2x = 14 + 6 = 20, so x = 10.",
      prior=prior("procedure", "compute", "wrong", "2x = 14 + 6 = 20")),
    # ======================= Physics =======================
    C("physics_early_stop_units", "Physics", "incomplete_early_stop", ("J",),
      "A car travels 150 km in 2.5 hours. What is its average speed in m/s?",
      "Average speed is 150 / 2.5 = 60 km/h. I'm not sure how to change km/h into m/s.",
      demonstrated="average speed in km/h",
      missing="converting 60 km/h to m/s (divide by 3.6)",
      error=None,
      expected_diagnosis="the speed is right in km/h; the unit conversion is missing",
      rationale="The computed value is correct in its unit; the student stops at the conversion.",
      trap_description="J: units step left open in its own sentence.",
      credit_quote="150 / 2.5 = 60", leak_forms=("16.7", "16.67")),
    C("physics_implicit_same_fall", "Physics", "incomplete_implicit_step", (),
      "A 2 kg ball and a 4 kg ball are dropped together with no air resistance. Using F = ma, explain why they "
      "hit the ground at the same time.",
      "The 4 kg ball has twice the weight, so it has twice the force on it. So they land together.",
      demonstrated="the heavier ball has twice the gravitational force",
      missing="it also has twice the mass, so a = F/m is the same for both",
      error=None,
      expected_diagnosis="the force comparison is right; the link through a = F/m is not stated",
      rationale="Twice the force alone would suggest a larger acceleration; the explanation the question asks for "
                "needs the mass to double too. The stated part is true.",
      trap_description="A valid start with the decisive inference left out.",
      credit_quote="twice the force"),
    C("physics_conceptual_forward_force", "Physics", "incorrect_conceptual", ("E",),
      "A hockey puck slides across frictionless ice at a constant velocity. What net force acts on it?",
      "I'm sure there must be a forward force on it, otherwise it would stop moving.",
      demonstrated="attends to the puck's motion",
      missing="constant velocity means zero net force (Newton's first law)",
      error="believes motion needs a continuing force",
      expected_diagnosis="a conceptual error: motion is taken to require a net force",
      rationale="The claim reflects the motion-implies-force idea, not a slip.",
      trap_description="E: certainty with a wrong physical idea.",
      error_quote="a forward force", leak_forms=("0 N", "net force is zero")),
    C("physics_local_error_force", "Physics", "incorrect_local_error", ("B", "I"),
      "A 1500 kg car accelerates from 0 to 20 m/s in 8 s. What net force acts on it?",
      "First the acceleration: a = (20 - 0) / 8 = 2.5 m/s^2. Then Newton's second law: F = m × a. "
      "So F = 1500 × 2.5 = 3250 N.",
      demonstrated="correct acceleration and the right law",
      missing="1500 × 2.5 = 3750",
      error="a multiplication slip",
      expected_diagnosis="sound physics; one arithmetic slip",
      rationale="Equation choice and substitution are right; only the product is wrong.",
      trap_description="B and I: the slip must not be read as a physics misconception.",
      credit_quote="a = (20 - 0) / 8 = 2.5", error_quote="1500 × 2.5 = 3250", leak_forms=("3750",)),
    C("physics_right_answer_mass_grows", "Physics", "correct_answer_wrong_reasoning", ("A",),
      "Two identical cars, one at 10 m/s and one at 20 m/s, brake with the same force. Which needs the longer "
      "distance to stop?",
      "The faster car needs a longer distance because it has more mass when it moves faster.",
      demonstrated="the right conclusion",
      missing="the faster car has more kinetic energy (or needs longer to lose its speed) at the same force",
      error="believes a car's mass increases with its speed",
      expected_diagnosis="the conclusion is right; the reason (mass grows with speed) is false",
      rationale="Identical cars have the same mass; the right answer rests on a false physical claim.",
      trap_description="A: right answer, false physical reason.",
      error_quote="more mass when it moves faster"),
    C("physics_right_reasoning_sign_slip", "Physics", "correct_reasoning_wrong_answer", ("C",),
      "A stone is dropped from rest. Taking upward as positive and g = 10 m/s^2, what is its velocity after 3 s?",
      "v = u + at with u = 0 and a = -10 m/s^2, so v = 0 + (-10)(3) = -30 m/s. So the answer is v = -3 m/s.",
      demonstrated="correct equation, signs and calculation",
      missing="copying -30 m/s as the final answer",
      error="a transcription slip in the final value",
      expected_diagnosis="the working is right; the final value is miscopied",
      rationale="The student computes -30 m/s correctly and then writes -3 m/s.",
      trap_description="C: sign and direction handled correctly; only the transcription is wrong.",
      credit_quote="(-10)(3) = -30", error_quote="v = -3 m/s"),
    C("physics_correct_average_speed_route", "Physics", "correct_work", (),
      "A ball is thrown straight up at 12 m/s. How high does it rise? (g = 10 m/s^2)",
      "It slows by 10 m/s every second, so it takes 1.2 s to stop. Its average speed on the way up is 6 m/s, so it "
      "rises 6 × 1.2 = 7.2 m.",
      demonstrated="a complete solution by time and average speed",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete, by a route other than v^2 = u^2 - 2gh",
      rationale="Under constant deceleration the average speed is half the initial speed, so the distance from "
                "time and average speed equals the standard result (144 / 20).",
      trap_description="A valid non-standard route: no gap may be invented."),
    C("physics_bare_weight", "Physics", "no_reasoning", ("D",),
      "What is the weight of a 3 kg mass on Earth? (g = 10 m/s^2)",
      "30 N.",
      demonstrated="a value only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare value shows neither understanding nor a specific gap.",
      trap_description="D: a correct bare answer."),
    C("physics_misconception_third_law", "Physics", "misconception", (),
      "A heavy truck and a small car collide head-on. Which one experiences the larger force during the collision?",
      "The car feels the larger force, because the truck is heavier and pushes harder.",
      demonstrated="compares the two vehicles",
      missing="the forces are equal and opposite (Newton's third law); the car's acceleration is larger",
      error="believes the heavier object exerts the larger force in an interaction",
      expected_diagnosis="a misconception about interaction forces",
      rationale="Contrasts with the local multiplication slip in this domain: here a physical principle is "
                "misunderstood.",
      trap_description="A deep, common misconception that must be named as conceptual.",
      error_quote="the truck is heavier and pushes harder", leak_forms=("forces are equal", "equal in size")),
    C("physics_repair_partial_direction", "Physics", "repair_followup", ("G",),
      "A ball is thrown straight up at 15 m/s. What is its velocity after 2 s? (g = 10 m/s^2)",
      "Gravity slows it on the way up, so I subtract: v = 15 - 10(2) = -5 m/s. A negative speed can't be right, "
      "so the answer is 5 m/s upward.",
      demonstrated="now subtracts gravity's effect correctly",
      missing="reading -5 m/s as 5 m/s downward",
      error="still misreads the direction given by the sign",
      expected_diagnosis="the sign in the equation is fixed, but the direction is still misread: not repaired",
      rationale="The earlier gap was the direction of gravity's effect. The equation is fixed, but the student "
                "rejects the negative result and calls the motion upward, so the direction idea is not repaired.",
      trap_description="G: one part fixed, the same underlying gap still open.",
      credit_quote="v = 15 - 10(2) = -5", error_quote="5 m/s upward", repair="partial",
      previous_attempt="v = 15 + 10(2) = 35 m/s.",
      prior=prior("concept", "set_up", "wrong", "v = 15 + 10(2) = 35 m/s")),
    # ======================= Biology =======================
    C("biology_early_stop_blood_sugar", "Biology", "incomplete_early_stop", ("J",),
      "A person eats a meal high in sugar. Explain how the body brings the blood sugar level back down.",
      "After the meal, sugar is absorbed into the blood, so the blood sugar level rises. I'm not sure what the body "
      "does about it.",
      demonstrated="the first link: absorption raises blood sugar",
      missing="the pancreas releases insulin and cells take up glucose",
      error=None,
      expected_diagnosis="the first link is right; the regulating mechanism is missing",
      rationale="The stated link is true and stated on its own; the regulation is not attempted.",
      trap_description="J: a correct causal link followed by a separate admission of not knowing.",
      credit_quote="the blood sugar level rises", leak_forms=("insulin",)),
    C("biology_implicit_deforestation", "Biology", "incomplete_implicit_step", (),
      "Explain why cutting down a large area of forest can increase the amount of carbon dioxide in the air. "
      "Give each link in the explanation.",
      "Trees take in carbon dioxide for photosynthesis. So cutting them down increases carbon dioxide in the air.",
      demonstrated="trees absorb carbon dioxide in photosynthesis",
      missing="fewer trees means less carbon dioxide is removed from the air",
      error=None,
      expected_diagnosis="the premise is right; the connecting link is not stated",
      rationale="The question asks for each link; the step from absorbing CO2 to less CO2 being removed is skipped.",
      trap_description="A causal chain with its middle link left implicit.",
      credit_quote="Trees take in carbon dioxide for photosynthesis"),
    C("biology_conceptual_mother_genes", "Biology", "incorrect_conceptual", ("E",),
      "Why do children inherit features from both of their parents?",
      "I'm certain we get all our genes from our mother, because the baby grows inside her; the father only decides "
      "if it is a boy or a girl.",
      demonstrated="links inheritance to genes",
      missing="each parent gives half of the chromosomes through the egg and the sperm",
      error="believes all genes come from the mother",
      expected_diagnosis="a conceptual error about how genes are inherited",
      rationale="A wrong model of inheritance, stated with certainty.",
      trap_description="E: confident and wrong.",
      error_quote="all our genes from our mother"),
    C("biology_local_error_punnett", "Biology", "incorrect_local_error", ("B",),
      "Two parents are both Aa, where A is dominant. What fraction of their children are expected to show the "
      "recessive trait?",
      "The cross gives AA, Aa, aA and Aa. Only aa would show the recessive trait, so the fraction is 0.",
      demonstrated="sets up the cross and knows only aa shows the recessive trait",
      missing="the fourth combination is aa, so the fraction is 1/4",
      error="a transcription slip: aa was written as Aa",
      expected_diagnosis="sound genetics; one miscopied combination",
      rationale="The rule (only aa shows the trait) is right; the slip is in listing the combinations.",
      trap_description="B: the slip must not be read as not understanding dominance.",
      credit_quote="Only aa would show the recessive trait", error_quote="AA, Aa, aA and Aa",
      leak_forms=("1/4", "one in four", "25%")),
    C("biology_right_answer_whale_size", "Biology", "correct_answer_wrong_reasoning", ("A",),
      "Is a whale a fish or a mammal? Explain.",
      "A mammal, because it is very large and fish are small.",
      demonstrated="the right classification",
      missing="whales breathe air with lungs, are warm-blooded and feed their young on milk",
      error="classifies by size, which is not a defining feature",
      expected_diagnosis="the classification is right; the reason is false",
      rationale="Size does not decide the class (whale sharks are large fish).",
      trap_description="A: right classification, false criterion.",
      error_quote="fish are small"),
    C("biology_right_reasoning_meiosis_slip", "Biology", "correct_reasoning_wrong_answer", ("C",),
      "A human body cell has 46 chromosomes. How many chromosomes does each gamete made by meiosis have?",
      "Meiosis halves the number of chromosomes, so each gamete has 46 ÷ 2 = 32.",
      demonstrated="knows meiosis halves the number",
      missing="46 ÷ 2 = 23",
      error="a slip in the final value",
      expected_diagnosis="the biology is right; the arithmetic is wrong",
      rationale="The halving rule is right; the digits of the result are swapped.",
      trap_description="C: understanding shown, wrong final value.",
      credit_quote="Meiosis halves the number of chromosomes", error_quote="46 ÷ 2 = 32",
      leak_forms=("23",)),
    C("biology_correct_oxygen_muscles", "Biology", "correct_work", (),
      "Explain why muscles need more oxygen during exercise, and how it reaches them.",
      "Muscles respire more during exercise to release more energy. Aerobic respiration uses oxygen, so the muscles "
      "need more oxygen, and red blood cells carry it there from the lungs.",
      demonstrated="the full mechanism and the transport",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete",
      rationale="Both parts of the question are answered correctly.",
      trap_description="Complete work: no gap may be invented."),
    C("biology_bare_chloroplast", "Biology", "no_reasoning", ("D",),
      "Which part of a plant cell carries out photosynthesis?",
      "Chloroplast.",
      demonstrated="a name only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="Recall alone shows no reasoning to diagnose.",
      trap_description="D: a correct bare answer."),
    C("biology_misconception_acquired_traits", "Biology", "misconception", (),
      "A man builds big muscles at the gym. Will his children be born with big muscles? Explain.",
      "Yes, because the muscles he built will be passed on to his children through his genes.",
      demonstrated="links inheritance to genes",
      missing="changes acquired during life do not change the genes passed on",
      error="believes acquired traits are inherited",
      expected_diagnosis="a misconception: acquired characteristics are inherited",
      rationale="Contrasts with the miscopied Punnett square: here the model of inheritance itself is wrong.",
      trap_description="A classic deep misconception.",
      error_quote="passed on to his children through his genes"),
    C("biology_repair_false_pulmonary", "Biology", "repair_followup", ("H",),
      "Does the pulmonary artery carry oxygen-rich or oxygen-poor blood? Explain using what defines an artery.",
      "I fixed it: the pulmonary artery is an artery, so it must carry oxygen-rich blood to the lungs.",
      demonstrated="claims a correction",
      missing="arteries are defined by carrying blood away from the heart; the pulmonary artery carries "
              "oxygen-poor blood",
      error="still defines arteries by oxygen content",
      expected_diagnosis="the same misconception repeated: not repaired",
      rationale="The student says they fixed it but repeats the same wrong definition.",
      trap_description="H: a claimed repair that repeats the error.",
      error_quote="it must carry oxygen-rich blood", repair="false",
      previous_attempt="Arteries carry oxygen-rich blood, so the pulmonary artery carries oxygen-rich blood.",
      prior=prior("concept", "set_up", "wrong", "Arteries carry oxygen-rich blood")),
    # ======================= History =======================
    C("history_early_stop_black_death", "History", "incomplete_early_stop", ("J",),
      "The Black Death (1347-1351) killed a large share of Europe's population. Explain how this could have led to "
      "higher wages for the peasants who survived.",
      "So many people died that there were far fewer workers left. I'm not sure how that connects to wages.",
      demonstrated="the labour shortage",
      missing="employers competed for scarce workers, so wages rose",
      error=None,
      expected_diagnosis="the first causal link is right; the link to wages is missing",
      rationale="A true cause is stated; the student says they cannot connect it.",
      trap_description="J: a valid cause and an open question in separate sentences.",
      credit_quote="far fewer workers left"),
    C("history_implicit_hastings", "History", "incomplete_implicit_step", (),
      "The Battle of Hastings was in 1066 and Magna Carta was sealed in 1215. Was Magna Carta sealed more or less "
      "than 150 years after Hastings? Show your working.",
      "Less than 150 years, because 1215 is before 1216.",
      demonstrated="the right comparison with 1216",
      missing="where 1216 comes from: 1066 + 150",
      error=None,
      expected_diagnosis="correct but the step 1066 + 150 = 1216 is not shown, and the question asks for working",
      rationale="The comparison is valid; the working the question asks for is left implicit.",
      trap_description="A valid jump with the needed calculation unstated.",
      credit_quote="1215 is before 1216"),
    C("history_conceptual_cold_war", "History", "incorrect_conceptual", (),
      "Did the USA and the Soviet Union fight each other directly in large battles during the Cold War? Explain.",
      "Yes, the Cold War was called a war because the American and Soviet armies fought big battles against each "
      "other in Europe.",
      demonstrated="links the name to conflict",
      missing="the Cold War was a rivalry without direct large-scale fighting between the two",
      error="misunderstands what the Cold War was",
      expected_diagnosis="a conceptual error about the nature of the Cold War",
      rationale="The claim misreads what defines the period, not a single date.",
      trap_description="A wrong idea of the event itself.",
      error_quote="armies fought big battles against each other"),
    C("history_local_error_interwar", "History", "incorrect_local_error", ("B",),
      "The First World War lasted from 1914 to 1918 and the Second from 1939 to 1945. How many years passed between "
      "the end of the first and the start of the second?",
      "The first war ended in 1918 and the second started in 1939. 1939 - 1918 = 11 years.",
      demonstrated="picks the right two dates",
      missing="1939 - 1918 = 21",
      error="a subtraction slip",
      expected_diagnosis="the right dates; one arithmetic slip",
      rationale="The chronology is understood; only the subtraction is wrong.",
      trap_description="B: a slip, not a chronology misconception.",
      credit_quote="ended in 1918 and the second started in 1939", error_quote="1939 - 1918 = 11",
      leak_forms=("21 years", "= 21")),
    C("history_right_answer_africa_first", "History", "correct_answer_wrong_reasoning", ("A",),
      "Which happened first: the building of the Great Pyramid of Giza or the founding of Rome? Explain.",
      "The Great Pyramid came first, because Egypt is in Africa and civilisations in Africa always came before those "
      "in Europe.",
      demonstrated="the right order",
      missing="the dates: the pyramid around 2560 BC, Rome traditionally 753 BC",
      error="an unsupported generalisation used as evidence",
      expected_diagnosis="the order is right; the reasoning is an invalid generalisation",
      rationale="The general rule is false and is not evidence for the order.",
      trap_description="A: right answer from an unsupported inference.",
      error_quote="always came before those in Europe"),
    C("history_right_reasoning_berlin_wall", "History", "correct_reasoning_wrong_answer", ("C",),
      "The Berlin Wall was built in 1961 and fell in 1989. For how many years did it stand?",
      "From 1961 to 1989 is 1989 - 1961, which is 28 years. So the wall stood for 26 years.",
      demonstrated="the right subtraction and value",
      missing="giving 28 as the answer",
      error="miscopies the final value",
      expected_diagnosis="the working is right; the final answer is miscopied",
      rationale="28 is computed and then 26 is written.",
      trap_description="C: correct reasoning, wrong final transcription.",
      credit_quote="1989 - 1961, which is 28 years", error_quote="stood for 26 years"),
    C("history_correct_shakespeare_light", "History", "correct_work", ("F",),
      "Could Shakespeare (1564-1616) have watched a play in a theatre lit by electric light? Explain using dates.",
      "I'm not totally sure, but I think no: Shakespeare died in 1616, and electric lighting was only invented in the "
      "1800s, more than 200 years later.",
      demonstrated="the right conclusion from the right dates",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete despite the stated doubt",
      rationale="The dates and the inference are right; the doubt is about confidence, not the work.",
      trap_description="F: hedging language on correct work must not be read as a gap."),
    C("history_bare_ww2_end", "History", "no_reasoning", ("D",),
      "In which year did the Second World War end?",
      "1945.",
      demonstrated="a date only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare date shows no reasoning.",
      trap_description="D: a correct bare answer."),
    C("history_misconception_correlation", "History", "misconception", (),
      "A historian finds that a town's population fell sharply in the same decade that a new king came to power. "
      "Does this show that the king caused the fall?",
      "Yes, it proves it: if the population fell when he came to power, he must have caused it.",
      demonstrated="notices the two events coincide",
      missing="happening at the same time does not show cause; other explanations need ruling out",
      error="treats coincidence in time as proof of cause",
      expected_diagnosis="a misconception about historical causation",
      rationale="Contrasts with the subtraction slip in this domain: a reasoning principle is misunderstood.",
      trap_description="An unsupported inference presented as proof.",
      error_quote="he must have caused it"),
    C("history_repair_genuine_columbus", "History", "repair_followup", (),
      "Could Christopher Columbus, who sailed in 1492, have read Charles Darwin's book on evolution, published in "
      "1859? Explain using the dates.",
      "No. Columbus sailed in 1492 and the book came out in 1859, which is 367 years later, so he could not have "
      "read it.",
      demonstrated="the right order and difference of the dates",
      missing="nothing",
      error=None,
      expected_diagnosis="the earlier chronology error is repaired with new work",
      rationale="Earlier the student placed the book before the voyage; now the order is right and justified.",
      trap_description="A genuine repair.",
      credit_quote="367 years later", repair="genuine",
      previous_attempt="Yes, because Darwin's book came out before Columbus sailed.",
      prior=prior("representation", "identify_quantities", "wrong", "Darwin's book came out before Columbus sailed")),
    # ======================= Programming =======================
    C("programming_early_stop_trace", "Programming", "incomplete_early_stop", ("J",),
      "What does this Python code print?\n\nx = 5\ny = x * 2\nx = y - 3\nprint(x, y)",
      "After the second line y is 10. I'm not sure what happens to x after that.",
      demonstrated="traces y correctly",
      missing="x becomes 10 - 3 = 7, so it prints 7 10",
      error=None,
      expected_diagnosis="the trace is right so far; the reassignment of x is not traced",
      rationale="The traced value is correct; the student stops at the next line.",
      trap_description="J: a correct trace and an open question in separate sentences.",
      credit_quote="y is 10", leak_forms=("7 10", "x is 7")),
    C("programming_implicit_binary_search", "Programming", "incomplete_implicit_step", (),
      "Explain why binary search needs the list to be sorted. Give the reason each step depends on.",
      "Because it compares the target with the middle element and then throws away half of the list.",
      demonstrated="describes the algorithm's step correctly",
      missing="discarding half is only safe because sorting guarantees the target cannot be in that half",
      error=None,
      expected_diagnosis="the description is right; the link to sortedness is not stated",
      rationale="The question asks why sorting is needed; the decisive link is left out, and nothing said is false.",
      trap_description="Algorithmic reasoning with its key inference implicit.",
      credit_quote="throws away half of the list"),
    C("programming_conceptual_aliasing", "Programming", "incorrect_conceptual", ("E",),
      "In Python, after running a = [1, 2] then b = a then b.append(3), what is a?",
      "I'm sure a is still [1, 2], because b = a makes a separate copy of the list.",
      demonstrated="reads the statements in order",
      missing="b = a makes both names refer to the same list, so a is [1, 2, 3]",
      error="believes assignment copies a list",
      expected_diagnosis="a conceptual error about references and copies",
      rationale="A wrong model of assignment, stated confidently.",
      trap_description="E: certainty with a wrong mental model.",
      error_quote="makes a separate copy", leak_forms=("[1, 2, 3]",)),
    C("programming_local_error_squares", "Programming", "incorrect_local_error", ("B", "I"),
      "What does f(4) return?\n\ndef f(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i * i\n"
      "    return total",
      "The loop goes i = 1, 2, 3, 4. It adds the squares: 1 + 4 + 9 + 16. That is 1 + 4 = 5, 5 + 9 = 14, "
      "14 + 16 = 31.",
      demonstrated="the right loop range and the right terms",
      missing="14 + 16 = 30",
      error="an addition slip while tracing",
      expected_diagnosis="the trace is right; one addition slip",
      rationale="The range and the squares are traced correctly; only the last sum is wrong.",
      trap_description="B and I: several valid steps then a slip; not an algorithmic misconception.",
      credit_quote="1 + 4 + 9 + 16", error_quote="14 + 16 = 31", leak_forms=("= 30", "is 30", "returns 30")),
    C("programming_right_answer_floor_division", "Programming", "correct_answer_wrong_reasoning", ("A",),
      "What does 10 // 3 give in Python? Explain.",
      "3, because // rounds to the nearest whole number, and 3.33 rounds to 3.",
      demonstrated="the right value",
      missing="// is floor division: it rounds down (11 // 3 is 3, not 4)",
      error="believes // rounds to the nearest integer",
      expected_diagnosis="the value is right; the meaning of // is wrong",
      rationale="Rounding to nearest happens to agree here but is not what // does.",
      trap_description="A: right output, false explanation.",
      error_quote="rounds to the nearest whole number"),
    C("programming_right_reasoning_index_sum", "Programming", "correct_reasoning_wrong_answer", ("C",),
      "What does this print?\n\nnums = [4, 8, 15]\nprint(nums[1] + nums[2])",
      "Indexing starts at 0, so nums[1] is 8 and nums[2] is 15. Their sum is 8 + 15 = 33.",
      demonstrated="correct indexing",
      missing="8 + 15 = 23",
      error="an addition slip",
      expected_diagnosis="indexing is understood; the sum is wrong",
      rationale="An execution slip, unlike an indexing misconception.",
      trap_description="C: correct reasoning, wrong final value.",
      credit_quote="nums[1] is 8 and nums[2] is 15", error_quote="8 + 15 = 33", leak_forms=("= 23", "is 23")),
    C("programming_correct_empty_list", "Programming", "correct_work", (),
      "Does this function crash for an empty list? Explain.\n\ndef first_or_none(xs):\n    if len(xs) == 0:\n"
      "        return None\n    return xs[0]",
      "No. For an empty list len(xs) is 0, so the if is true and it returns None before it ever reaches xs[0], so it "
      "never indexes an empty list.",
      demonstrated="edge-case reasoning through the guard",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete",
      rationale="The guard is traced correctly for the edge case.",
      trap_description="Complete edge-case reasoning: no gap may be invented."),
    C("programming_bare_power", "Programming", "no_reasoning", ("D",),
      "What does print(2 ** 3) output?",
      "8",
      demonstrated="a value only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare output shows no reasoning.",
      trap_description="D: a correct bare answer."),
    C("programming_misconception_range_end", "Programming", "misconception", (),
      "A loop should add the numbers 1 to 10, but this code gives 45. Why?\n\ntotal = 0\nfor i in range(1, 10):\n"
      "    total += i",
      "range(1, 10) includes 10, so the loop adds 1 to 10, which should be 55; the computer must have made an "
      "addition mistake.",
      demonstrated="knows the intended sum is 55",
      missing="range stops before its end value, so 10 is never added",
      error="believes range includes its end value",
      expected_diagnosis="an algorithmic misconception about range, unlike the tracing slips in this domain",
      rationale="The bug is explained away by a wrong belief about range.",
      trap_description="A misconception that blames the machine instead of the model of the code.",
      error_quote="range(1, 10) includes 10"),
    C("programming_repair_partial_indexing", "Programming", "repair_followup", ("G",),
      "This code should add up every number in xs. Fix it.\n\ntotal = 0\nfor i in range(1, len(xs) + 1):\n"
      "    total += xs[i]",
      "I fixed the crash by using range(1, len(xs)), so it no longer goes past the end of the list.",
      demonstrated="fixes the out-of-range index",
      missing="the loop must start at 0, otherwise xs[0] is skipped",
      error="still starts at index 1",
      expected_diagnosis="one part of the indexing gap is fixed, the start index is still wrong: not repaired",
      rationale="The crash is fixed, but the corrected code still skips the first element, so the indexing gap "
                "is only partly repaired.",
      trap_description="G: a partial repair.",
      credit_quote="no longer goes past the end of the list", error_quote="range(1, len(xs))", repair="partial",
      previous_attempt="range(1, len(xs) + 1) visits every element, so the code is fine.",
      prior=prior("concept", "set_up", "wrong", "range(1, len(xs) + 1) visits every element")),
    # ======================= Chemistry =======================
    C("chemistry_early_stop_water_mass", "Chemistry", "incomplete_early_stop", ("J",),
      "How many grams of water are produced when 4 g of hydrogen gas (H2) burns completely? 2H2 + O2 → 2H2O",
      "The molar mass of H2 is 2 g/mol, so 4 g is 4 / 2 = 2 mol of H2. I don't know how to get from there to the "
      "water.",
      demonstrated="moles of hydrogen",
      missing="2 mol H2 gives 2 mol H2O, which is 36 g",
      error=None,
      expected_diagnosis="the mole calculation is right; the ratio and mass step are missing",
      rationale="The first stoichiometric step is correct and separate from the stated stop.",
      trap_description="J: valid work and a stop in separate sentences.",
      credit_quote="4 / 2 = 2 mol", leak_forms=("36 g", "= 36")),
    C("chemistry_implicit_ionic_melting", "Chemistry", "incomplete_implicit_step", (),
      "Explain why salt (NaCl) has a much higher melting point than ice. Compare the forces that must be overcome.",
      "Salt is held together by ionic bonds. So it melts at a higher temperature.",
      demonstrated="names the bonding in salt",
      missing="the comparison: strong ionic bonds versus the weaker forces between water molecules in ice",
      error=None,
      expected_diagnosis="the bonding is right; the comparison the question asks for is missing",
      rationale="The question asks to compare forces; only one side is given. Nothing stated is false.",
      trap_description="A molecular explanation with the decisive comparison left out.",
      credit_quote="held together by ionic bonds"),
    C("chemistry_conceptual_candle_wax", "Chemistry", "incorrect_conceptual", (),
      "When a candle burns, it gets shorter. Where does the wax go?",
      "The wax is destroyed by the flame, it just stops existing.",
      demonstrated="notices the wax is used up",
      missing="the wax reacts with oxygen to form carbon dioxide and water vapour; matter is conserved",
      error="believes burning destroys matter",
      expected_diagnosis="a conceptual error about conservation of mass in combustion",
      rationale="A wrong idea of what burning does, not a slip.",
      trap_description="A non-conservation idea.",
      error_quote="it just stops existing"),
    C("chemistry_local_error_molar_mass", "Chemistry", "incorrect_local_error", ("B", "I"),
      "What is the molar mass of carbon dioxide (CO2)? (C = 12, O = 16)",
      "CO2 has one carbon and two oxygens. Carbon gives 12. The two oxygens give 2 × 16 = 32. "
      "Adding them: 12 + 32 = 46 g/mol.",
      demonstrated="the right atoms and the right partial masses",
      missing="12 + 32 = 44",
      error="an addition slip",
      expected_diagnosis="the chemistry is right; one arithmetic slip",
      rationale="Composition and partial masses are right; only the final sum is wrong.",
      trap_description="B and I: several valid steps then a slip; not a chemistry misconception.",
      credit_quote="2 × 16 = 32", error_quote="12 + 32 = 46", leak_forms=("= 44", "44 g/mol")),
    C("chemistry_right_answer_liquids", "Chemistry", "correct_answer_wrong_reasoning", ("A",),
      "Is water (H2O) a compound or an element? Explain.",
      "A compound, because it is a liquid, and all liquids are compounds.",
      demonstrated="the right classification",
      missing="water is a compound because it contains two elements chemically bonded",
      error="classifies by state of matter (mercury and bromine are liquid elements)",
      expected_diagnosis="the classification is right; the reason is false",
      rationale="State of matter does not decide element or compound.",
      trap_description="A: right answer, false general rule.",
      error_quote="all liquids are compounds"),
    C("chemistry_right_reasoning_balance_slip", "Chemistry", "correct_reasoning_wrong_answer", ("C",),
      "Balance the equation H2 + O2 → H2O. What coefficient goes in front of H2O?",
      "There are 2 oxygen atoms on the left, so I need 2 H2O on the right. That makes 4 hydrogens on the right, so I "
      "need 2 H2 on the left. So the coefficient of H2O is 4.",
      demonstrated="balances oxygen and hydrogen correctly",
      missing="the coefficient of H2O is 2",
      error="reports the hydrogen count instead of the coefficient",
      expected_diagnosis="the balancing is right; the final answer is miscopied",
      rationale="The student sets 2 H2O and then writes 4.",
      trap_description="C: correct balancing, wrong final value.",
      credit_quote="I need 2 H2O on the right", error_quote="the coefficient of H2O is 4"),
    C("chemistry_correct_moles_unsure", "Chemistry", "correct_work", ("F",),
      "How many moles are in 22 g of carbon dioxide (CO2, molar mass 44 g/mol)?",
      "I'm not confident about this, but moles = mass / molar mass = 22 / 44 = 0.5 mol.",
      demonstrated="the right relation and value",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete despite the stated doubt",
      rationale="The calculation is right; the doubt is about confidence.",
      trap_description="F: doubt on correct work must not become a gap."),
    C("chemistry_bare_ph", "Chemistry", "no_reasoning", ("D",),
      "What is the pH of pure water at 25 °C?",
      "7.",
      demonstrated="a value only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare value shows no reasoning.",
      trap_description="D: a correct bare answer."),
    C("chemistry_misconception_burning_mass", "Chemistry", "misconception", (),
      "Steel wool is burned in air and turns into iron oxide. Is the product heavier or lighter than the original "
      "steel wool? Explain.",
      "Lighter, because burning always destroys some of the material, so things lose mass when they burn.",
      demonstrated="compares the masses",
      missing="the iron combines with oxygen from the air, so the product is heavier",
      error="believes burning always removes mass",
      expected_diagnosis="a misconception about mass in reactions, unlike the addition slip in this domain",
      rationale="A general belief drives the wrong answer.",
      trap_description="A deep misconception versus a local slip.",
      error_quote="burning always destroys some of the material"),
    C("chemistry_repair_false_dissolving", "Chemistry", "repair_followup", ("H",),
      "10 g of salt is dissolved in 100 g of water. What is the mass of the solution?",
      "I see my mistake: the salt doesn't disappear, it turns into water, so the solution still weighs 100 g.",
      demonstrated="claims a correction",
      missing="the salt's mass stays in the solution: 110 g",
      error="still loses the salt's mass",
      expected_diagnosis="the same conservation error repeated: not repaired",
      rationale="The student claims to fix the idea but still drops the salt's mass.",
      trap_description="H: a claimed repair that repeats the error.",
      error_quote="still weighs 100 g", leak_forms=("110",), repair="false",
      previous_attempt="The salt disappears when it dissolves, so the solution is 100 g.",
      prior=prior("concept", "set_up", "wrong", "The salt disappears when it dissolves")),
    # ======================= Logic / critical reasoning =======================
    C("logic_early_stop_squares_chain", "Logic / critical reasoning", "incomplete_early_stop", ("J",),
      "Premises: All squares are rectangles. All rectangles have four right angles. Some of the shapes on this page "
      "are squares. What can you conclude about some of the shapes on this page?",
      "From the first two premises, all squares have four right angles. I'm not sure how the third premise fits in.",
      demonstrated="a valid inference from the first two premises",
      missing="combining it with the third: some shapes on the page have four right angles",
      error=None,
      expected_diagnosis="the first inference is valid and must be credited; the last inference is missing",
      rationale="Built to catch the v1 failure: a valid inference followed by a separate sentence of doubt.",
      trap_description="J: the valid inference must be credited as its own step, not merged into the stuck one.",
      credit_quote="all squares have four right angles"),
    C("logic_implicit_hidden_premise", "Logic / critical reasoning", "incomplete_implicit_step", (),
      "Explain why this argument is valid, stating any premise it relies on: 'All metals conduct electricity. So this "
      "spoon conducts electricity.'",
      "Because metals conduct electricity, the spoon conducts electricity.",
      demonstrated="uses the stated premise",
      missing="the hidden premise: the spoon is made of metal",
      error=None,
      expected_diagnosis="the stated premise is used correctly; the hidden premise is not stated",
      rationale="The question asks for the premises relied on; the needed one is left implicit.",
      trap_description="Hidden premise: a valid-looking jump with an unstated assumption.",
      credit_quote="metals conduct electricity"),
    C("logic_conceptual_undistributed_middle", "Logic / critical reasoning", "incorrect_conceptual", (),
      "Is this argument valid? 'Some students are athletes. Some athletes are musicians. Therefore some students are "
      "musicians.'",
      "Yes, it is valid, because the athletes link the students to the musicians.",
      demonstrated="sees a shared middle term",
      missing="the athletes who are students may not be the athletes who are musicians",
      error="treats a shared middle term with 'some' as a valid link",
      expected_diagnosis="an invalid inference judged valid",
      rationale="The conclusion does not follow; the student's justification is the fallacy itself.",
      trap_description="Invalid inference accepted as valid.",
      error_quote="Yes, it is valid"),
    C("logic_local_error_truth_value", "Logic / critical reasoning", "incorrect_local_error", ("B",),
      "If p is true and q is false, what is the truth value of (p and q) or (not q)?",
      "p and q is false, because q is false. not q is true. So we get false or true, which is false.",
      demonstrated="evaluates both parts correctly",
      missing="false or true is true",
      error="a slip in the last connective",
      expected_diagnosis="both parts are right; the final 'or' is evaluated wrongly",
      rationale="The sub-results are correct; only the last evaluation is wrong.",
      trap_description="B: a local slip in a logic calculation.",
      credit_quote="not q is true", error_quote="false or true, which is false"),
    C("logic_right_answer_cold_feathers", "Logic / critical reasoning", "correct_answer_wrong_reasoning", ("A",),
      "Premises: All birds have feathers. A penguin is a bird. Does a penguin have feathers? Explain.",
      "Yes, because penguins live in cold places, and animals in cold places have feathers to stay warm.",
      demonstrated="the right conclusion",
      missing="the conclusion follows directly from the two given premises",
      error="reasons from a false generalisation instead of the premises",
      expected_diagnosis="the conclusion is right; the reasoning does not use the premises and is false",
      rationale="Polar bears live in the cold without feathers; the given premises are ignored.",
      trap_description="A: right conclusion, invalid reasoning.",
      error_quote="animals in cold places have feathers"),
    C("logic_right_reasoning_truth_table_rows", "Logic / critical reasoning", "correct_reasoning_wrong_answer", ("C",),
      "How many rows does a truth table with 3 variables have?",
      "Each variable can be true or false, so each one doubles the rows: 2 × 2 × 2. That gives 6 rows.",
      demonstrated="the doubling reasoning",
      missing="2 × 2 × 2 = 8",
      error="a slip in the final product",
      expected_diagnosis="the reasoning is right; the final value is wrong",
      rationale="The doubling argument is right; only the product is wrong.",
      trap_description="C: correct reasoning, wrong final value.",
      credit_quote="2 × 2 × 2", error_quote="That gives 6 rows", leak_forms=("8 rows", "= 8")),
    C("logic_correct_prime_counterexample", "Logic / critical reasoning", "correct_work", ("F",),
      "Is the claim 'every prime number is odd' true? Justify your answer.",
      "I'm not sure if this counts, but 2 is a prime number and it is even, so the claim is false.",
      demonstrated="a valid counterexample",
      missing="nothing",
      error=None,
      expected_diagnosis="valid and complete despite the stated doubt",
      rationale="One counterexample refutes a universal claim.",
      trap_description="F: doubt on correct work must not become a gap."),
    C("logic_bare_modus_ponens", "Logic / critical reasoning", "no_reasoning", ("D",),
      "Is this argument valid? 'If A then B. A. Therefore B.'",
      "Yes.",
      demonstrated="a verdict only",
      missing="any reasoning",
      error=None,
      expected_diagnosis="no evidence of reasoning: no gap label",
      rationale="A bare yes shows no reasoning.",
      trap_description="D: a correct bare answer."),
    C("logic_misconception_converse", "Logic / critical reasoning", "misconception", (),
      "It is true that 'if a shape is a square, it has four sides.' Is it then also true that 'if a shape has four "
      "sides, it is a square'? Explain.",
      "Yes, because if a statement is true, then reversing it is always true too.",
      demonstrated="relates the two statements",
      missing="the converse of a true statement can be false (a rectangle has four sides)",
      error="believes the converse of a true conditional is always true",
      expected_diagnosis="a misconception about conditionals, unlike the evaluation slip in this domain",
      rationale="A general wrong rule drives the answer.",
      trap_description="A deep misconception versus a local slip.",
      error_quote="reversing it is always true"),
    C("logic_repair_genuine_four_legs", "Logic / critical reasoning", "repair_followup", (),
      "'If an animal is a dog, it has four legs. My pet has four legs. So my pet is a dog.' Is this argument valid? "
      "Explain.",
      "No, it is not valid. Having four legs doesn't make an animal a dog, because a cat has four legs too, so the "
      "conclusion doesn't follow.",
      demonstrated="a counterexample showing the conclusion does not follow",
      missing="nothing",
      error=None,
      expected_diagnosis="the earlier invalid inference is repaired with new work",
      rationale="Earlier the student accepted the argument; now they refute it with a counterexample.",
      trap_description="A genuine repair.",
      credit_quote="a cat has four legs too", repair="genuine",
      previous_attempt="Yes, it is valid, so my pet must be a dog.",
      prior=prior("concept", "choose_method", "wrong", "Yes, it is valid")),
]
