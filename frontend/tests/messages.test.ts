import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiError } from "@/lib/api";
import { friendlyError, nextProgressAt, progressLine } from "@/lib/messages";
import { ErrorCard } from "@/components/session/Cards";

describe("friendly error sentences", () => {
  it.each([
    ["model_unavailable", "Cognify is still thinking. Try again."],
    ["timeout", "Cognify is still thinking. Try again."],
    ["network", "Can't reach Cognify. Check the connection."],
    ["unknown_session", "This session was lost (the server restarted). Start a new problem to continue."],
    ["invalid_request", "That answer could not be sent. Shorten it and try again."],
    ["malformed_response", "Something went wrong."],
    ["anything_new", "Something went wrong."],
  ])("%s", (code, sentence) => expect(friendlyError(code)).toBe(sentence));

  it("the card shows the sentence, keeps the code small, and offers Try again only when retryable", () => {
    const retryable = renderToStaticMarkup(createElement(ErrorCard, { error: new ApiError("model_unavailable", "Please try again.", true, 503), onRetry: () => {} }));
    expect(retryable).toContain("Cognify is still thinking. Try again.");
    expect(retryable).toContain("model_unavailable · 503");
    expect(retryable).toContain("Try again");
    expect(retryable).not.toContain("Please try again.");

    const final = renderToStaticMarkup(createElement(ErrorCard, { error: new ApiError("invalid_request", "Too long.", false, 422) }));
    expect(final).toContain("That answer could not be sent");
    expect(final).not.toContain("btn-main");
  });

  it("a lost session (backend restarted) offers to start the same problem again", () => {
    const lost = renderToStaticMarkup(createElement(ErrorCard, { error: new ApiError("unknown_session", "No session with that id.", false, 404), onRestart: () => {} }));
    expect(lost).toContain("This session was lost");
    expect(lost).toContain("Start this problem again");
    expect(lost).not.toContain("Try again");
  });
});

describe("waiting lines", () => {
  it("only the dots for the first 5 seconds, then one line after another", () => {
    expect(progressLine(0)).toBeNull();
    expect(progressLine(4_999)).toBeNull();
    expect(progressLine(5_000)).toBe("Reading your answer…");
    expect(progressLine(12_000)).toBe("Choosing a way to teach…");
    expect(progressLine(60_000)).toBe("Checking the reply…");
  });

  it("knows when the next line is due, and when there are no more", () => {
    expect(nextProgressAt(0)).toBe(5_000);
    expect(nextProgressAt(5_000)).toBe(12_000);
    expect(nextProgressAt(20_000)).toBeNull();
  });
});
