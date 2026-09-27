// Phase I10 - cross-tab invalidation contract.
//
// The module is deliberately tested with a tiny BroadcastChannel double:
// messages are schema-checked, state-free, fail-soft, and never delivered
// back to the publishing tab.

import assert from "node:assert/strict";

const channels = [];
class FakeBroadcastChannel {
  constructor(name) {
    this.name = name;
    this.onmessage = null;
    channels.push(this);
  }

  postMessage(data) {
    for (const peer of channels) {
      if (peer !== this && peer.name === this.name && peer.onmessage) {
        queueMicrotask(() => peer.onmessage({ data }));
      }
    }
  }
}

globalThis.BroadcastChannel = FakeBroadcastChannel;
const sync = await import("../web/studio-sync.js?i10-unit");

assert.equal(sync.STUDIO_SYNC_CHANNEL, "comfymodal-studio");
assert.deepEqual(sync.STUDIO_SYNC_KINDS, ["settings", "workspace", "history", "workflows"]);
assert.equal(sync.isStudioSyncKind("history"), true);
assert.equal(sync.isStudioSyncKind("unknown"), false);
assert.equal(sync.isStudioSyncMessage({ kind: "history", at: 1 }), true);
assert.equal(sync.isStudioSyncMessage({ kind: "history", at: "1" }), false);
assert.equal(sync.isStudioSyncMessage({ kind: "unknown", at: 1 }), false);
assert.equal(sync.isStudioSyncMessage({ kind: "history", at: -1 }), false);

const received = [];
const unsubscribe = sync.subscribeStudioSync("settings", (message) => received.push(message));
const secondSettingsListener = sync.subscribeStudioSync("settings", () => {
  throw new Error("listener failure must be isolated");
});
const external = new FakeBroadcastChannel("comfymodal-studio");
assert.equal(channels.length, 2, "one shared channel plus one external tab");

assert.equal(sync.publishStudioSync("settings"), true);
assert.equal(sync.publishStudioSync("not-a-kind"), false);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(received.length, 0, "the publishing tab does not receive its own message");

external.postMessage({ kind: "settings", at: 123 });
external.postMessage({ kind: "settings", at: 123, state: { forbidden: true } });
external.postMessage({ kind: "history", at: 123 });
external.postMessage({ kind: "settings", at: "bad" });
external.postMessage({ kind: "bogus", at: 123 });
await new Promise((resolve) => setImmediate(resolve));
assert.deepEqual(received, [
  { kind: "settings", at: 123 },
  { kind: "settings", at: 123, state: { forbidden: true } },
]);

unsubscribe();
secondSettingsListener();
assert.equal(sync.subscribeStudioSync("bogus", () => {})("ignored"), undefined);
console.log("PASS: I10 cross-tab sync validates, isolates, and unsubscribes");
