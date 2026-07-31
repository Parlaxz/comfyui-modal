import assert from "node:assert/strict";
import { getLastFiniteSeed, cryptoRandomSeed } from "../web/studio-feature-registry.js";

assert.equal(getLastFiniteSeed([100]), 100);
assert.equal(getLastFiniteSeed([100, 50]), 50);
assert.equal(getLastFiniteSeed([100, "", "invalid"]), 100);
assert.equal(getLastFiniteSeed(["", null, "invalid"]), null);

const increment = (values) => (getLastFiniteSeed(values) ?? 0) + 1;
const decrement = (values) => (getLastFiniteSeed(values) ?? 0) - 1;
assert.equal(increment([100]), 101);
assert.equal(increment([100, 50]), 51);
assert.equal(decrement([100, 50]), 49);
assert.equal(increment(["", "invalid"]), 1);
assert.equal(decrement(["", "invalid"]), -1);

for (let i = 0; i < 32; i += 1) {
  const value = cryptoRandomSeed(2147483647);
  assert.equal(Number.isInteger(value), true);
  assert.equal(value >= 0 && value <= 2147483647, true);
}

console.log("PASS: seed insertion helpers preserve last-finite and valid random-seed semantics");
