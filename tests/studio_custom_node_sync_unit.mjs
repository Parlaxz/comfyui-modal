// Modal Studio custom-node sync frontend unit tests.
//
// Deterministic Node tests: no browser, network, deploy, or backend runtime.
// The decision table exercises the pure message projection used by the
// Deployment section; the API checks use an in-memory fetch response.

import assert from "node:assert/strict";
import { customNodeSyncMessages } from "../web/studio-backend-deployment.js";
import {
  getCustomNodeSyncStatus,
  triggerPushPlugins,
  triggerRebuildDependencies,
} from "../web/studio-backend-api.js";

const clean = {
  status: "ok",
  payload_state: "exact",
  local_only: [],
  published_only: [],
  duplicates: [],
  unknown_identity: [],
  dependencies_changed: [],
  receipt_schema_supported: true,
  local_generation: null,
  published_generation: null,
};

function ids(data) {
  return customNodeSyncMessages({ ...clean, ...data }).map((message) => message.id);
}

// Every inventory_state × dependencies_state combination has an explicit
// expectation. A known dependency change remains actionable even when the
// inventory authority is unknown; the unknown inventory itself never becomes
// an inventory drift warning.
for (const inventory_state of ["match", "differs", "ambiguous", "unknown"]) {
  for (const dependencies_state of ["same", "changed", "unknown"]) {
    const data = { inventory_state, dependencies_state };
    if (inventory_state === "differs") data.local_only = [{ name: "node-a" }];
    if (dependencies_state === "changed") data.dependencies_changed = ["node-a", "node-b"];

    const actual = ids(data);
    const expected = [];
    if (inventory_state === "unknown") expected.push("unknown");
    if (inventory_state === "differs") expected.push("local-only");
    if (dependencies_state === "changed") expected.push("dependencies");
    if (dependencies_state === "unknown") expected.push("dependencies-unknown");
    if (inventory_state === "ambiguous") expected.push("identity");
    if (!expected.length) expected.push("clear");
    assert.deepEqual(actual, expected, `${inventory_state} × ${dependencies_state}`);
    if (inventory_state === "unknown") {
      assert.equal(actual.includes("local-only"), false, "unknown inventory has no drift warning");
    }
  }
}
console.log("PASS: inventory_state × dependencies_state decision table");

assert.deepEqual(
  ids({ inventory_state: "match", payload_state: "unknown", dependencies_state: "same" }),
  ["unknown"],
  "unknown payload suppresses payload drift messaging"
);
assert.match(
  customNodeSyncMessages({
    ...clean,
    inventory_state: "differs",
    local_only: [{ name: "node-a" }, { name: "node-b" }],
    dependencies_state: "changed",
    dependencies_changed: ["node-a"],
  }).map((message) => message.text).join(" "),
  /2 plugins.*not yet published.*Push plugins.*1 plugin has changed dependencies.*Rebuild dependencies/
);
assert.deepEqual(
  ids({ inventory_state: "match", dependencies_state: "same", duplicates: [{ identity: "x", names: ["a", "b"] }] }),
  ["identity"],
  "identity ambiguity stays a separate note"
);
console.log("PASS: payload unknown, counts, and identity note contracts");

const previousFetch = globalThis.fetch;
const calls = [];
globalThis.fetch = async (url, options) => {
  calls.push({ url: String(url), method: (options && options.method) || "GET" });
  return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
};
try {
  await getCustomNodeSyncStatus("/comfymodal");
  await triggerPushPlugins("/comfymodal");
  await triggerRebuildDependencies("/comfymodal");
} finally {
  globalThis.fetch = previousFetch;
}
assert.deepEqual(calls, [
  { url: "/comfymodal/custom-nodes/sync-status", method: "GET" },
  { url: "/comfymodal/custom-nodes/sync", method: "POST" },
  { url: "/comfymodal/custom-nodes/sync/rebuild-dependencies", method: "POST" },
]);
console.log("PASS: custom-node sync API helper routes");
