import { expect, test } from "vitest";
import { errorMessage } from "./api";

test("errorMessage reads the API's detail in either shape", () => {
  expect(errorMessage({ detail: "Files can be up to 500 MB." })).toBe("Files can be up to 500 MB.");
  expect(errorMessage({ detail: [{ msg: "Field required", loc: ["body", "file"] }] })).toBe(
    "Field required",
  );
  expect(errorMessage({ detail: [] })).toBeNull();
  expect(errorMessage("Internal Server Error")).toBeNull();
  expect(errorMessage(null)).toBeNull();
});
