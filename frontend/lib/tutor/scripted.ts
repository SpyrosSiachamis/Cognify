/* The prepared scenario: the rectangle problem, with copy identical to the prototype. */

import type { Answer, TutorService } from "./types";

const RECTANGLE_ANSWER: Answer = {
  result: ["Dimensions: ", { b: "6 m × 8 m" }],
  steps: [
    ["Let the width be ", { m: "x" }, ". The length is ", { m: "x + 2" }, "."],
    ["Area gives ", { eq: "x(x + 2) = 48" }],
    ["Rearrange to ", { eq: "x² + 2x − 48 = 0" }],
    ["Factor ", { eq: "(x + 8)(x − 6) = 0" }, ", so ", { m: "x = 6" }, ". A width cannot be negative."],
  ],
};

export const scriptedTutor: TutorService = {
  source: "scripted",
  async answer() {
    return RECTANGLE_ANSWER;
  },
};
