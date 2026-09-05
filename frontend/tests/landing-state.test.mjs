import assert from "node:assert/strict";
import test from "node:test";

import { landingPrimaryAction } from "../src/lib/landingState.ts";

test("signed-out visitors receive the guest experience action", () => {
  assert.deepEqual(landingPrimaryAction(null), { kind: "guest", label: "以访客身份体验" });
});

test("signed-in users receive the workspace action", () => {
  assert.deepEqual(landingPrimaryAction({ id: "owner", kind: "owner", expiresAt: null }), {
    kind: "workspace",
    label: "进入工作台",
    to: "/ai/news",
  });
});
