// Focused source contract for the frontend-only remote inventory poller.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.join(import.meta.dirname, "..");
const settings = fs.readFileSync(path.join(root, "web", "studio-settings.js"), "utf8");
const workflows = fs.readFileSync(path.join(root, "web", "studio-workflows.js"), "utf8");

assert.match(settings, /comfymodal_remote_inventory_refresh_interval_s/);
assert.match(settings, /REMOTE_INVENTORY_REFRESH_DEFAULT = "300"/);
assert.match(settings, /\["0", "Off"\].*\["60", "1 minute"\].*\["300", "5 minutes"\].*\["900", "15 minutes"\].*\["1800", "30 minutes"\]/s);
assert.match(settings, /MODERN_SETTINGS_KEYS[\s\S]*comfymodal_remote_inventory_refresh_interval_s/);
assert.match(settings, /interface:[\s\S]*REMOTE_INVENTORY_REFRESH_KEY/);

assert.match(workflows, /refreshRemoteInventory/);
assert.match(workflows, /root\.isConnected/);
assert.match(workflows, /document\.visibilityState === "visible"/);
assert.match(workflows, /document\.hasFocus\(\)/);
assert.match(workflows, /studioModalVisible/);
assert.match(workflows, /root\.closest\("\.comfymodal-testing-overlay"\)/);
assert.match(workflows, /inventoryPollInFlight/);
assert.match(workflows, /removeEventListener\("visibilitychange", reconcileInventoryPoller\)/);
assert.match(workflows, /removeEventListener\("focus", reconcileInventoryPoller\)/);
assert.match(workflows, /removeEventListener\("blur", reconcileInventoryPoller\)/);

console.log("PASS: remote inventory settings and poller source contracts");
