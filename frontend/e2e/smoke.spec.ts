import { expect, test } from "@playwright/test";
import { makeWav } from "./wav";

// Needs the API and worker running with fake providers (see the README and CI).
test("upload a recording, read the notes and rename a speaker", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Recording").setInputFiles({
    name: "standup.wav",
    mimeType: "audio/wav",
    buffer: makeWav(4),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/meetings\/\d+$/);
  await expect(page.getByText("Fake summary of the meeting.")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Speaker 1" }).first().click();
  await page.getByLabel("Speaker name").fill("Asha");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Asha" }).first()).toBeVisible();
});
