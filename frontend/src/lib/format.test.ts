import { describe, expect, test } from "vitest";
import { formatDuration, formatTimestamp } from "./format";

describe("formatTimestamp", () => {
  test("minutes and seconds under an hour, hours above", () => {
    expect(formatTimestamp(0)).toBe("0:00");
    expect(formatTimestamp(134_000)).toBe("2:14");
    expect(formatTimestamp(3_723_000)).toBe("1:02:03");
  });
});

describe("formatDuration", () => {
  test("rounds to minutes, never below one", () => {
    expect(formatDuration(20)).toBe("1 min");
    expect(formatDuration(2220)).toBe("37 min");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });
});
