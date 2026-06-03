"""Quick sanity check for __init__.py restore_timing code."""
import sys
sys.path.insert(0, ".")

with open("__init__.py") as f:
    content = f.read()

checks = [
    'result.get("_restore_timing"',
    "_finish_job(task_key, prompt_id, outputs, success=True, meta=",
    '"restore_timing": result.get("_restore_timing"',
]

for check in checks:
    if check in content:
        print(f"OK: {check}")
    else:
        print(f"MISSING: {check}")

# Also check _finish_job signature
if "def _finish_job(item_id: int, prompt_id: str, outputs: dict, success: bool, meta: dict | None = None):" in content:
    print("OK: _finish_job signature with meta parameter")
else:
    print("MISSING: _finish_job meta parameter")

print("Done")
