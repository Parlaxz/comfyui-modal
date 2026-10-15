// Modal Studio — golden-deploy failure-tail unit tests.
//
// Deterministic Node coverage (no browser, no network, no timers) for
// deployFailureTail in web/studio-backend-api.js: the merged v2ctl
// stdout+stderr blob must surface the real error line, never a stale
// banner such as "DEPLOYING TO=...".
//
// Run: node tests/studio_deploy_failure_tail_unit.mjs

import assert from "node:assert/strict";

import { deployFailureTail } from "../web/studio-backend-api.js";

function section(name) {
  console.log("PASS: " + name);
}

// Misordered capture from a block-buffered child: unbuffered stderr lands
// before the flushed stdout preflight. The tail must be the ERROR, not the
// banner (this exact blob reproduced the reported dropdown title).
const misordered = [
  "ERROR: deploy lock is held by another process; refusing to acquire",
  "[v2ctl.destination.preflight]",
  "DEPLOYING TO=Testing 6 (ws_175a616152c5)",
  "",
].join("\n");
assert.equal(
  deployFailureTail(misordered),
  "ERROR: deploy lock is held by another process; refusing to acquire"
);
section("misordered stderr-first blob surfaces the ERROR line");

// Chronological capture (unbuffered child): ERROR is already last.
const ordered = [
  "[v2ctl.destination.preflight]",
  "DEPLOYING TO=Testing 6 (ws_175a616152c5)",
  "ERROR: deploy lock is held by another process; refusing to acquire",
].join("\n");
assert.equal(
  deployFailureTail(ordered),
  "ERROR: deploy lock is held by another process; refusing to acquire"
);
section("chronological blob keeps the trailing ERROR line");

// Python traceback: the exception line, not "Traceback (most recent call...)".
const traceback = [
  "[v2ctl.deploy] profile=golden_p1_parallel_c0_p8_h100",
  "Traceback (most recent call last):",
  '  File "cli.py", line 1, in <module>',
  "LockHeldError: deploy lock is held by another process",
].join("\n");
assert.equal(
  deployFailureTail(traceback),
  "LockHeldError: deploy lock is held by another process"
);
section("traceback blob surfaces the exception line");

// CRLF (Windows child) and lone-CR progress rewrites normalize to lines.
assert.equal(
  deployFailureTail("line one\r\nDEPLOYING TO=Testing 6 (ws_1)\r\nERROR: boom\r\n"),
  "ERROR: boom"
);
assert.equal(
  deployFailureTail("progress 10%\rprogress 40%\rERROR: boom"),
  "ERROR: boom"
);
section("CRLF and lone-CR separators normalize");

// No error line anywhere: fall back to the last non-empty line.
assert.equal(
  deployFailureTail("[v2ctl.deploy] exit=1 manifest=/tmp/x.json\n"),
  "[v2ctl.deploy] exit=1 manifest=/tmp/x.json"
);
section("error-free blob falls back to the last line");

// Empty / missing output degrades to "" so callers show their fallback.
assert.equal(deployFailureTail(""), "");
assert.equal(deployFailureTail("   \n  \n"), "");
assert.equal(deployFailureTail(null), "");
assert.equal(deployFailureTail(undefined), "");
section("empty output degrades to empty string");

console.log("All deploy failure-tail unit tests passed.");
