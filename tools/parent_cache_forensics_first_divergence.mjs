#!/usr/bin/env node

import { readFile } from "node:fs/promises"
import { pathToFileURL } from "node:url"

const UNAVAILABLE = "unavailable"

function samePrefix(before, after) {
  if (!Array.isArray(before) || !Array.isArray(after) || after.length < before.length) return false
  return before.every((item, index) => item?.fingerprint === after[index]?.fingerprint)
}

function firstDifferent(before, after, key = "fingerprint") {
  const left = Array.isArray(before) ? before : []
  const right = Array.isArray(after) ? after : []
  const limit = Math.min(left.length, right.length)
  for (let index = 0; index < limit; index += 1) {
    if (left[index]?.[key] !== right[index]?.[key]) return index
  }
  return left.length === right.length ? null : limit
}

function changed(before, after) {
  return before !== UNAVAILABLE && after !== UNAVAILABLE && before !== after
}

function classifyMessage(before, after) {
  const oldItems = before?.messageItems
  const newItems = after?.messageItems
  if (!changed(before?.messageFingerprint, after?.messageFingerprint)) return null
  if (samePrefix(oldItems, newItems)) {
    return {
      category: "message",
      classification: "suffix-only",
      firstDivergenceIndex: oldItems.length,
      reason: "new-appended-messages-only",
    }
  }
  return {
    category: "message",
    classification: "early-message-change",
    firstDivergenceIndex: firstDifferent(oldItems, newItems),
    contentClassification: UNAVAILABLE,
    instructionChange: UNAVAILABLE,
    skillChange: UNAVAILABLE,
    reason: "content-is-sanitized-and-cannot-be-categorized",
  }
}

export function classifyAdjacent(before, after) {
  const changes = []
  const messageChange = classifyMessage(before, after)
  if (messageChange) changes.push(messageChange)

  if (changed(before?.systemFingerprint, after?.systemFingerprint)) {
    changes.push({
      category: "system",
      classification: "early-system-change",
      firstDivergenceIndex: firstDifferent(before?.systemItems, after?.systemItems, "hash"),
    })
  }

  if (changed(before?.orderedToolFingerprint, after?.orderedToolFingerprint)) {
    changes.push({
      category: "tool",
      classification: "ordered-tool-change",
      firstDivergenceIndex: firstDifferent(before?.toolObservations, after?.toolObservations, "nameHash"),
    })
  }

  if (changed(before?.providerOptionKeyFingerprint, after?.providerOptionKeyFingerprint)) {
    changes.push({
      category: "provider-options",
      classification: "provider-option-key-change",
      beforeKeys: before?.providerOptionKeys ?? UNAVAILABLE,
      afterKeys: after?.providerOptionKeys ?? UNAVAILABLE,
    })
  }

  if (changed(before?.promptCacheKey?.hash, after?.promptCacheKey?.hash)
    || before?.promptCacheKey?.presence !== after?.promptCacheKey?.presence) {
    changes.push({
      category: "cache-key",
      classification: "prompt-cache-key-change",
      beforePresence: before?.promptCacheKey?.presence ?? UNAVAILABLE,
      afterPresence: after?.promptCacheKey?.presence ?? UNAVAILABLE,
    })
  }

  if (before?.request?.model !== after?.request?.model || before?.request?.provider !== after?.request?.provider) {
    if (before?.request?.model !== UNAVAILABLE || after?.request?.model !== UNAVAILABLE) {
      changes.push({ category: "model", classification: "model-provider-change" })
    }
  }

  return {
    schemaVersion: 1,
    recordType: "first-divergence",
    beforeTimestamp: before?.timestamp ?? UNAVAILABLE,
    afterTimestamp: after?.timestamp ?? UNAVAILABLE,
    beforeHookStage: before?.hookStage ?? UNAVAILABLE,
    afterHookStage: after?.hookStage ?? UNAVAILABLE,
    firstDivergence: changes[0] ?? { category: "none", classification: "no-observed-change" },
    changes,
    instructionChange: UNAVAILABLE,
    skillChange: UNAVAILABLE,
    dcpChange: UNAVAILABLE,
    finalSerializedHttpBodyChange: UNAVAILABLE,
  }
}

export function parseManifests(text) {
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((record) => record.recordType === "manifest")
}

export async function analyzeFile(path) {
  const text = await readFile(path, "utf8")
  const manifests = parseManifests(text)
  return manifests.slice(1).map((manifest, index) => classifyAdjacent(manifests[index], manifest))
}

const isMain = process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url
if (isMain) {
  const input = process.argv[2]
  if (!input) {
    console.error("usage: node parent_cache_forensics_first_divergence.mjs <observations.jsonl>")
    process.exitCode = 2
  } else {
    try {
      const findings = await analyzeFile(input)
      for (const finding of findings) process.stdout.write(`${JSON.stringify(finding)}\n`)
    } catch {
      console.error("unable-to-analyze-sanitized-manifest")
      process.exitCode = 1
    }
  }
}
