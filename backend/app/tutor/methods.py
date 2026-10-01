"""What each teaching method requires of a reply, in plain words.

The verifier receives the chosen method's definition, so it judges whether the reply
actually delivers the method (by what the move does, not by the words it uses).
"""

from app.common.vocab import Strategy

METHOD_DEFINITIONS: dict[Strategy, str] = {
    "socratic": (
        "One guiding question, built on what the student has, that leads them to work out the next step "
        "themselves. It may point their attention at a quantity, relation or case, as long as it asks rather "
        "than tells. No sketch to make, no worked example, no explanation."
    ),
    "visual_decomposition": (
        "The reply has the student lay the situation out in parts (a drawing, list, table, timeline or "
        "labelled diagram), with what they already know and what they want kept separate, and then asks "
        "about what that layout shows. A plain question with nothing to lay out does not count."
    ),
    "worked_example": (
        "The reply shows a different, simpler example and actually works its steps out (the reasoning "
        "written down, not just the question), then stops before the last step, which is the same kind of "
        "step the student is missing, and asks the student to do that step. Posing a simpler problem without "
        "working it does not count. It never works this problem."
    ),
    "analogy": (
        "The reply compares the situation to a familiar everyday one and asks a question that carries the "
        "comparison back to the problem."
    ),
    "counterexample": (
        "The reply shows a concrete case where the student's belief or step would give a clearly impossible "
        "result, and asks the student about it."
    ),
    "representation_switch": (
        "The reply asks the student to move what they have into another form (words, equation, graph, "
        "table) where the missing link is easier to see."
    ),
    "micro_hint": "The smallest pointer at the exact step, in one short sentence, with no explanation.",
}
