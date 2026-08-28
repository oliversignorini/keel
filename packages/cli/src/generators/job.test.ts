import { describe, expect, it } from "vitest";

import { GeneratorError, parseSteps } from "./job.js";

describe("parseSteps", () => {
  it("defaults to a single 'run' step when nothing is given", () => {
    expect(parseSteps(undefined)).toEqual(["run"]);
    expect(parseSteps("")).toEqual(["run"]);
    expect(parseSteps("   ")).toEqual(["run"]);
  });

  it("splits and trims a comma-separated list", () => {
    expect(parseSteps("fetch, aggregate ,publish")).toEqual(["fetch", "aggregate", "publish"]);
  });

  it("rejects a step name that is not snake_case", () => {
    expect(() => parseSteps("Fetch")).toThrow(GeneratorError);
    expect(() => parseSteps("fetch-data")).toThrow(GeneratorError);
    expect(() => parseSteps("2fetch")).toThrow(GeneratorError);
  });

  it("rejects a repeated step name", () => {
    expect(() => parseSteps("fetch,fetch")).toThrow(GeneratorError);
  });
});
