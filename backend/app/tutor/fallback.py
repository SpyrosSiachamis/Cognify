"""The safe fallback, explained: when no teaching draft passed, code says why it needs another answer.

Built only from the diagnosis the turn already has (no model call, so nothing new to verify). It quotes only the
student's own words, never the solution, the error analysis or an internal label, so it can reveal nothing the
student has not written. It claims uncertainty only when the student said so, and it does not ask again for work
the student already sent: when the diagnosis could not place real work, it says so and the trace flags it.
"""

import re
from typing import Literal

from .evidence import substantive
from .language import FALLBACK_REPLY, Language
from .schema import Step, TutorDiagnosis

FallbackKind = Literal[
    "student_uncertain",  # the student said they are unsure: start from that part
    "incorrect_step",  # a step the student wrote does not hold: check that one
    "missing_step",  # work is there, a step between or after is not
    "missing_reasoning",  # an answer with no working
    "unrecognized_evidence",  # the student wrote working, but it could not be placed on this problem's steps
    "general",  # nothing more specific to say
]

# Said in so many words; "I think" or "maybe" are not taken as uncertainty.
UNSURE = re.compile(
    r"\b(not (really |totally |completely |very |so )?sure|unsure|least sure|not certain|uncertain|confused|"
    r"(do not|don't|dont) (know|understand|get)|no idea|i'?m stuck)\b"
    r"|δεν είμαι σίγουρ|δεν ειμαι σιγουρ|δεν (το )?(ξέρω|ξερω|καταλαβαίνω|καταλαβαινω)|μπερδ",
    re.I,
)
ROLE_ORDER = ["identify_quantities", "choose_method", "set_up", "substitute", "compute", "interpret"]
MAX_QUOTE = 90

TEXT: dict[Language, dict[str, str]] = {
    "English": {
        "student_uncertain": 'You said: "{said}". Let\'s check that part first. Write how you would work it out, '
                             "step by step, even if you are not sure yet.",
        "incorrect_step": 'Not yet: one step does not hold up yet: "{step}". Look at that step again and show me '
                          "how you work it out.",
        "missing_step": 'Not yet: I can see "{after}", but I need to see how you got there{from_part}. Show me the '
                        "step that leads to it.",
        "missing_step_next": 'Not yet: I can follow your work up to "{before}", but the next step is not there yet. '
                             "Show me what you do next.",
        "missing_reasoning": "Not yet: I have your answer, but I need to see the calculation you used to get it.",
        "unrecognized_evidence": "I could not match your working to the steps of this problem yet. Please write it "
                                 "once more as one calculation for this problem, from its numbers to your answer.",
        "general": FALLBACK_REPLY["English"],
    },
    "Greek": {
        "student_uncertain": 'Έγραψες: "{said}". Ας δούμε πρώτα αυτό το σημείο. Γράψε πώς θα το έλυνες, βήμα '
                             "βήμα, ακόμα κι αν δεν είσαι σίγουρος.",
        "incorrect_step": 'Όχι ακόμα: ένα βήμα δεν στέκει ακόμα: "{step}". Κοίτα ξανά αυτό το βήμα και δείξε μου '
                          "πώς το υπολογίζεις.",
        "missing_step": 'Όχι ακόμα: βλέπω το "{after}", αλλά πρέπει να δω πώς έφτασες εκεί{from_part}. Δείξε μου '
                        "το βήμα που οδηγεί σε αυτό.",
        "missing_step_next": 'Όχι ακόμα: μπορώ να ακολουθήσω τη δουλειά σου μέχρι το "{before}", αλλά το επόμενο '
                             "βήμα λείπει. Δείξε μου τι κάνεις μετά.",
        "missing_reasoning": "Όχι ακόμα: έχω την απάντησή σου, αλλά πρέπει να δω τον υπολογισμό που σε οδήγησε εκεί.",
        "unrecognized_evidence": "Δεν μπόρεσα ακόμα να αντιστοιχίσω τη δουλειά σου με τα βήματα αυτού του "
                                 "προβλήματος. Γράψ' την ξανά ως έναν υπολογισμό για αυτό το πρόβλημα, από τους "
                                 "αριθμούς του μέχρι την απάντησή σου.",
        "general": FALLBACK_REPLY["Greek"],
    },
}
FROM_PART: dict[Language, str] = {"English": ' from "{before}"', "Greek": ' από το "{before}"'}


def _short(text: str) -> str:
    text = " ".join(text.split()).strip(" .,;:")
    return text if len(text) <= MAX_QUOTE else text[: MAX_QUOTE - 1].rstrip() + "…"


def _said_unsure(student_text: str) -> str | None:
    """The sentence in which the student said they are unsure, if they did."""
    for sentence in re.split(r"(?<=[.!?;\n])\s+", student_text):
        if UNSURE.search(sentence):
            return _short(sentence)
    return None


def _order(step: Step) -> int:
    return ROLE_ORDER.index(step.role)


def explain_fallback(
    diagnosis: TutorDiagnosis, gap_step: Step | None, student_text: str, language: Language,
    previous_message: str | None = None,
) -> tuple[str, FallbackKind]:
    """The fallback reply for this turn and what kind of explanation it is."""
    text = TEXT[language]
    said = _said_unsure(student_text)
    if said:
        return text["student_uncertain"].format(said=said), "student_uncertain"

    wrong = [s for s in diagnosis.steps if s.status == "wrong" and s.quote]
    if wrong:
        step = gap_step if gap_step in wrong else wrong[0]
        return text["incorrect_step"].format(step=_short(step.quote or "")), "incorrect_step"

    # An answer to the tutor's sub-question is work on this problem too (only its asked steps are kept).
    read_as_work = diagnosis.evidence == "sufficient" and diagnosis.response_to in ("original_problem", "tutor_question")
    if not read_as_work:
        if substantive(student_text):
            # Working was sent but could not be placed on this problem: asking for it again as if it were
            # missing would be wrong, so the reply says the matching failed (and the trace flags it).
            return text["unrecognized_evidence"], "unrecognized_evidence"
        if re.search(r"\d", student_text):
            return text["missing_reasoning"], "missing_reasoning"
        return text["general"], "general"

    quoted = sorted((s for s in diagnosis.steps if s.status == "correct" and s.quote), key=_order)
    missing = gap_step if gap_step is not None and gap_step.status == "missing" else next(
        (s for s in diagnosis.steps if s.status == "missing"), None)
    if missing is not None and quoted:
        before = [s for s in quoted if _order(s) < _order(missing)]
        after = [s for s in quoted if _order(s) > _order(missing)]
        if after:
            from_part = FROM_PART[language].format(before=_short(before[-1].quote or "")) if before else ""
            reply = text["missing_step"].format(after=_short(after[-1].quote or ""), from_part=from_part)
        else:
            reply = text["missing_step_next"].format(before=_short(quoted[-1].quote or ""))
        kind: FallbackKind = "missing_step"
    elif missing is not None:
        reply, kind = text["missing_reasoning"], "missing_reasoning"
    else:
        reply, kind = text["general"], "general"
    if previous_message is not None and reply == previous_message and substantive(student_text):
        # The student answered this very request with working, and it was still not placed: asking the same thing
        # again would hide that, so the reply says the matching failed (and the trace flags it).
        return text["unrecognized_evidence"], "unrecognized_evidence"
    return reply, kind
