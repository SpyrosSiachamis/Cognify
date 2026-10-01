"""The teaching methods, in two separate parts.

- MethodDefinition: what the method means, what the tutor and the student each do, and ONE decisive
  test: a yes/no question about the reply's behaviour that decides whether the method was performed.
  The teaching step and the verifier both receive it; the verifier's method check asks exactly that
  question. A single decisive test, rather than a list of clauses, keeps the judgement stable.
  It describes behaviour, never wording, counts or response shape.
- Guidance: ways the teaching step might carry the method out. Only the teaching step receives it,
  and it is advice, not an acceptance test.

Master-wide rules (no answer leak, no heavy hint, one new idea, one teaching move, the student does
the thinking) are not part of any method: the verifier checks them separately for every reply.
"""

from dataclasses import dataclass

from app.common.vocab import Strategy


@dataclass(frozen=True)
class MethodDefinition:
    meaning: str
    tutor_does: str
    student_does: str
    decisive_test: str  # one yes/no question about the reply: yes means the method was performed

    def render(self) -> str:
        return (
            f"Meaning: {self.meaning}\n"
            f"Tutor does: {self.tutor_does}\n"
            f"Student does: {self.student_does}\n"
            f"Decisive test: {self.decisive_test}"
        )


DEFINITIONS: dict[Strategy, MethodDefinition] = {
    "socratic": MethodDefinition(
        meaning="The student reasons their own way to the next step because the tutor asks rather than tells.",
        tutor_does="asks question(s) that build on what the student already has and lead toward the step at the gap.",
        student_does="works out the step by answering.",
        decisive_test="Does the reply move the student toward the step by asking, so that the step itself is left for the student to produce, rather than telling or explaining it?",
    ),
    "visual_decomposition": MethodDefinition(
        meaning="Making the structure of the situation visible, so the relation the student needs can be seen.",
        tutor_does="sets the situation out as a structure of parts (for example a sketch, table, columns, timeline "
        "or labelled list) that separates what is known from what is wanted.",
        student_does="finds the needed relation by reading or working with that structure.",
        decisive_test="Does the reply give the student a structure of the situation (for example a sketch, table, list or timeline) to look at or build, so that relating its parts is left to the student?",
    ),
    "worked_example": MethodDefinition(
        meaning="Learning from a solved case of the same kind, then transferring its reasoning.",
        tutor_does="shows a different, analogous case with its reasoning actually worked out.",
        student_does="carries that reasoning over to the step they are missing (for example by finishing the example "
        "or applying it to their own case).",
        decisive_test="Does the reply actually work out a different, analogous case, leaving the transfer to the student's own missing step for them?",
    ),
    "analogy": MethodDefinition(
        meaning="Understanding the unfamiliar through a familiar situation that has the same structure.",
        tutor_does="offers a familiar situation whose structure matches the point at the gap.",
        student_does="maps the familiar structure back onto their problem.",
        decisive_test="Does the reply map the point at the gap onto a familiar situation with the same structure, leaving the mapping back to the student?",
    ),
    "counterexample": MethodDefinition(
        meaning="A belief is revised because a concrete case shows it fails.",
        tutor_does="presents a concrete case where the student's belief or step leads to an impossible or "
        "contradictory result.",
        student_does="recognises the contradiction and revises the belief.",
        decisive_test="Does the reply put the student's own belief or step against a concrete case where it fails, leaving the revision to the student?",
    ),
    "representation_switch": MethodDefinition(
        meaning="Changing representation so the relation the student needs becomes easier to see.",
        tutor_does="directs the student to move what they have into another representation (words, equation, graph, "
        "table or similar).",
        student_does="makes the new representation and reads the relation from it.",
        decisive_test="Does the reply move the student into a different representation of what they have, leaving the making and reading of it to them?",
    ),
    "micro_hint": MethodDefinition(
        meaning="The smallest possible pointer at exactly the place where the student is stuck.",
        tutor_does="points at one specific thing at the gap.",
        student_does="does the step themselves.",
        decisive_test="Is the reply's help a minimal pointer aimed at exactly the place where the student is stuck?",
    ),
}

# Teaching-only advice: possible ways to carry each method out. Not an acceptance test.
GUIDANCE: dict[Strategy, str] = {
    "socratic": "A single well-aimed question often works; a short sequence of small questions that climbs to the "
    "step is also fine. Build the question on the student's own words or result.",
    "visual_decomposition": "Pick whatever structure suits the problem: a sketch to draw, a table or columns, a "
    "timeline, a labelled list. You may lay it out yourself (including values the student already found) or ask "
    "the student to build it. Mark what is wanted as unknown where that makes sense, and point the student at what "
    "the structure shows.",
    "worked_example": "Choose a simpler case of the same kind. Write its reasoning as short steps. A common pattern "
    "is to stop before the example's last step and hand that step to the student; another is to work it fully and "
    "ask the student to do the same on their own case.",
    "analogy": "Choose an everyday situation the student surely knows, whose structure matches the point at the gap. "
    "Keep the comparison short, then hand the mapping back.",
    "counterexample": "Use the student's own belief or step, push it onto a case where it clearly breaks (an "
    "impossible number, a contradiction), and let the student notice.",
    "representation_switch": "Name the representation to move to and what goes into it; leave the making and the "
    "reading to the student.",
    "micro_hint": "Point at the exact quantity, term or step, as briefly as possible.",
}

# The semantic definition per method: what the teaching step and the verifier both receive.
METHOD_DEFINITIONS: dict[Strategy, str] = {method: d.render() for method, d in DEFINITIONS.items()}
