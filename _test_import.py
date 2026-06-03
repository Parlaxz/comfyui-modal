"""Quick test: import __init__, verify _finish_job has meta param."""
import sys
import os

NODE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(NODE_DIR)
COMFYUI_ROOT = os.path.dirname(PARENT)

sys.path.insert(0, COMFYUI_ROOT)

# Verify the source file has the right signature
with open(os.path.join(NODE_DIR, "__init__.py"), "r", encoding="utf-8") as f:
    content = f.read()

if "def _finish_job(item_id: int, prompt_id: str, outputs: dict, success: bool, meta: dict | None = None):" in content:
    print("OK: _finish_job has meta param in source")
else:
    print("ERROR: _finish_job does NOT have meta param in source")
    # Find the actual signature
    for line in content.split("\n"):
        if "def _finish_job" in line:
            print(f"  Found: {line.strip()}")

if '"_restore_timing"' in content:
    print("OK: _restore_timing key found in source")
else:
    print("ERROR: _restore_timing key NOT found in source")

if "_finish_job_meta_keys.log" in content:
    print("OK: diagnostic file write found in source")
else:
    print("ERROR: diagnostic file write NOT found in source")

# Check line count
lines = content.split("\n")
print(f"Source file: {len(lines)} lines")

# Print the _finish_job function
print("\n--- _finish_job function ---")
in_func = False
for i, line in enumerate(lines, 1):
    if "def _finish_job" in line:
        in_func = True
    if in_func:
        print(f"  {i}: {line}")
        if in_func and line.strip() == "" and i > lines.index("def _finish_job") + 1:
            break
        if in_func and i - lines.index(next(l for l in lines if "def _finish_job" in l)) > 30:
            break

print("\n--- meta construction in success path ---")
for i, line in enumerate(lines, 1):
    if "_finish_job(task_key, prompt_id, outputs, success=True, meta=" in line or '_meta = {' in line or '"_restore_timing"' in line:
        print(f"  {i}: {line}")
