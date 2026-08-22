import test from "node:test"
import assert from "node:assert/strict"
import { classifyAdjacent } from "./parent_cache_forensics_first_divergence.mjs"

const base = {
  timestamp: "2026-08-20T00:00:00.000Z",
  hookStage: "experimental.chat.messages.transform",
  messageFingerprint: "sha256:messages-a",
  messageItems: [
    { fingerprint: "sha256:item-a" },
    { fingerprint: "sha256:item-b" },
  ],
  systemFingerprint: "sha256:system-a",
  systemItems: [{ hash: "sha256:system-item-a" }],
  orderedToolFingerprint: "sha256:tools-a",
  toolObservations: [{ nameHash: "sha256:tool-a" }],
  providerOptionKeyFingerprint: "sha256:options-a",
  providerOptionKeys: ["temperature"],
  promptCacheKey: { presence: "absent", hash: "unavailable" },
  request: { model: "model-a", provider: "provider-a" },
}

test("appended messages are suffix-only", () => {
  const after = {
    ...base,
    timestamp: "2026-08-20T00:00:01.000Z",
    messageFingerprint: "sha256:messages-b",
    messageItems: [...base.messageItems, { fingerprint: "sha256:item-c" }],
  }
  const finding = classifyAdjacent(base, after)
  assert.equal(finding.firstDivergence.classification, "suffix-only")
})

test("an early message change never guesses instruction or skill", () => {
  const after = {
    ...base,
    messageFingerprint: "sha256:messages-b",
    messageItems: [{ fingerprint: "sha256:item-x" }, base.messageItems[1]],
  }
  const finding = classifyAdjacent(base, after)
  assert.equal(finding.firstDivergence.classification, "early-message-change")
  assert.equal(finding.firstDivergence.instructionChange, "unavailable")
  assert.equal(finding.firstDivergence.skillChange, "unavailable")
})

test("observable system, tool, option, cache, and model changes are classified", () => {
  const after = {
    ...base,
    systemFingerprint: "sha256:system-b",
    orderedToolFingerprint: "sha256:tools-b",
    toolObservations: [{ nameHash: "sha256:tool-b" }],
    providerOptionKeyFingerprint: "sha256:options-b",
    providerOptionKeys: ["temperature", "promptCacheKey"],
    promptCacheKey: { presence: "present", hash: "sha256:cache-b" },
    request: { model: "model-b", provider: "provider-b" },
  }
  const finding = classifyAdjacent(base, after)
  assert.deepEqual(finding.changes.map((change) => change.category), ["system", "tool", "provider-options", "cache-key", "model"])
})
