# Screens

Each phase and view, mapped to a screen. Phase names are from `API_CONTRACT.md`.

## Screen map

| Screen | When | Features |
|---|---|---|
| Problem Inbox | Start. Paste a problem (2000 characters), subject chips, "Try an example" | F1 |
| Depth Selector | After Continue. Two cards: Answer and Master. "Edit problem" | F2 |
| Level 1 Answer | Result and short steps, "does not count as mastery evidence" note. Only button: **Switch to Master** | F3 |
| Master workspace | One screen that changes with the phase (below) | F6-F16 |
| Gap Reveal | Shown inside the workspace after the first diagnosis (phase `teach`) | F9 |
| Stress Test | Inside the workspace, phase `stress_test` | F15 |
| Verdict moment | Inside the workspace, phase `verdict` | F16, F21 |
| My Learning | Two tabs: Understanding Map (`GET /api/learner/{id}`) and How You Learn (`GET /api/strategies/{id}`) | F18, F19, F23 |
| Sidebar placeholders | History, Concept Map, Profile: hidden or one short line | F23 |

### Master workspace by phase

| Phase | What the student sees |
|---|---|
| `ask_first_thought` | The question "What would you try first?" and a text box. No help yet |
| `teach` | Gap Reveal (main gap, quoted evidence, confidence label), the method and its reason, one small teaching move, reply-check badge |
| `stress_test` | The follow-up problem only, no hints, "support removed" line |
| `verdict` | VERIFIED or NOT YET with evidence and both views' changes |
| `exited` | The solution, and a note that nothing was recorded |

## Look

Library background, cream cards, serif headings, sidebar from the mockups.

| Colour | Meaning |
|---|---|
| Green | **Only VERIFIED** |
| Navy and gold | Buttons and the selected level (never green) |
| Amber | In progress |
| Warm red | Gaps |

Never shaming: say what is missing, not what is wrong with the student.

## Microcopy

| Phase or moment | Text |
|---|---|
| `ask_first_thought` | "Before I help, what would you try first? Even an incomplete idea is useful." |
| Empty first thought | One short question, no explanation |
| Gap Reveal | "Here is where it got stuck, in your own words:" then the quote |
| Method with history | "Worked 7 of 9 times for you on recognition gaps." |
| Experiment | "Trying something different this time." (labelled on screen) |
| `stress_test` | "Now I am removing the support. New problem, same underlying idea, different surface." |
| VERIFIED | "You solved it on your own." |
| NOT YET | "Not yet. Here is what we will try differently." |

## Badges

- **"Seeded demo history"** on every view that shows seeded data (when `is_seeded` is true).
- **Reply-check badge**, small, under each tutor message, from `reply_check`. Example: "no answer leaked, method: visual (experiment)".

## States

- **Thinking:** a calm "Thinking about your answer..." with no streaming text; the reply appears whole after it is checked.
- **Empty:** My Learning with no concepts says "Nothing here yet. Solve a problem in Master to start."
- **Error:** show the error message; if `retryable` is true, a Try again button. A screen never crashes on a bad model reply.

## Signature animation (F21)

At the verdict the concept chip turns from fragile to verified (green) while the strategy count ticks up (7 of 9 becomes 8 of 10), in one moment. Both values come from `verdict.changes`. Smooth on a projector.
