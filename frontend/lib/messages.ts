/* Plain words for the student. Pure functions, so they are easy to test. */

/** A friendly sentence for an error code (the technical code is still shown, small, under it). */
export function friendlyError(code: string): string {
  switch (code) {
    case "model_unavailable":
    case "timeout":
      return "Cognify is still thinking. Try again.";
    case "network":
      return "Can't reach Cognify. Check the connection.";
    case "unknown_session":
      return "This session was lost (the server restarted). Start a new problem to continue.";
    case "invalid_request":
      return "That answer could not be sent. Shorten it and try again.";
    default:
      return "Something went wrong.";
  }
}

// While a turn is on its way. The backend streams nothing, so these are only timed messages.
const PROGRESS: { after: number; line: string }[] = [
  { after: 5_000, line: "Reading your answer…" },
  { after: 12_000, line: "Choosing a way to teach…" },
  { after: 20_000, line: "Checking the reply…" },
];

/** The progress line to show after waiting `elapsedMs`, or null for just the typing dots. */
export function progressLine(elapsedMs: number): string | null {
  let line: string | null = null;
  for (const step of PROGRESS) if (elapsedMs >= step.after) line = step.line;
  return line;
}

/** When the next line is due (ms after the start), or null when there are no more. */
export function nextProgressAt(elapsedMs: number): number | null {
  return PROGRESS.find((step) => step.after > elapsedMs)?.after ?? null;
}
