#!/usr/bin/env node
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const webDir = path.join(root, "web");

const files = readdirSync(webDir).filter(f => f.endsWith(".js"));

let totalInteractive = 0;
const inventories = [];
const allControls = [];

// Scan for interactive patterns
const patterns = [
  { name: "button_creation", regex: /\bel\s*\(\s*["']button["']/g, label: "el button" },
  { name: "data-testid", regex: /data-testid[\"']?\s*[:=]\s*[\"']([^\"']+)[\"']/g, label: "testid" },
  { name: "onclick", regex: /onclick\s*:/g, label: "onclick" },
  { name: "addEventListener", regex: /addEventListener\s*\(\s*[\"']click[\"']/g, label: "click listener" },
  { name: "data-page", regex: /data-page/g, label: "nav button" },
  { name: "role_button", regex: /role.*button/g, label: "role button" },
];

for (const file of files) {
  const content = readFileSync(path.join(webDir, file), "utf-8");
  const lines = content.split("\n");
  let fileControls = 0;
  // Find all data-testid values
  const testidRegex = /data-testid["'\s]*[:=]+\s*["']([^"']+)["']/g;
  let m;
  while ((m = testidRegex.exec(content)) !== null) {
    const lineNum = content.slice(0, m.index).split("\n").length;
    allControls.push({
      file,
      line: lineNum,
      testid: m[1],
      snippet: lines[lineNum - 1]?.trim().slice(0, 120) || "",
      kind: "testid",
    });
    fileControls++;
  }
  // Find el button creations
  const elBtnRegex = /el\s*\(\s*["']button["']/g;
  while ((m = elBtnRegex.exec(content)) !== null) {
    const lineNum = content.slice(0, m.index).split("\n").length;
    // Don't double-count if already has testid on same line
    const ctx = content.slice(Math.max(0, m.index - 300), m.index + 300);
    if (!ctx.includes("data-testid")) {
      allControls.push({
        file,
        line: lineNum,
        testid: null,
        snippet: lines[lineNum - 1]?.trim().slice(0, 120) || "",
        kind: "button_no_testid",
      });
      fileControls++;
    }
  }
  if (fileControls > 0) inventories.push({ file, count: fileControls });
}

console.log("Files with controls:", inventories.length);
console.log("Total controls (approx):", allControls.length);
console.log("\nBy file:");
for (const inv of inventories.sort((a, b) => b.count - a.count)) {
  console.log(`  ${inv.file}: ${inv.count}`);
}

// Write raw inventory
writeFileSync(path.join(__dirname, "raw-source-inventory.json"), JSON.stringify(allControls, null, 2));
console.log("\nWrote raw-source-inventory.json with", allControls.length, "entries");

// Now also scan for specific interactive categories
const categories = {};
for (const c of allControls) {
  const key = c.file.replace(".js", "");
  categories[key] = (categories[key] || 0) + 1;
}
console.log("\nCategories by module:", JSON.stringify(categories, null, 2));
