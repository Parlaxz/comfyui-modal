"""Check the latest benchmark run's response for restore_timing."""
import json
from pathlib import Path

runs_dir = Path("benchmark_runs")
latest = sorted(runs_dir.iterdir())[-1]
print(f"Latest run: {latest.name}")

run2_file = latest / "run2_response.json"
with open(run2_file) as f:
    data = json.load(f)

meta = data.get("history", {}).get("meta", {})
print(f"meta keys: {list(meta.keys())}")
print(f"restore_timing: {meta.get('restore_timing', '__ABSENT')}")
trace = meta.get("trace", {})
print(f"trace keys: {list(trace.keys())}")
print(f"restore in trace: {'restore' in trace}")

# Also check run1
run1_file = latest / "run1_response.json"
with open(run1_file) as f:
    data1 = json.load(f)
meta1 = data1.get("history", {}).get("meta", {})
print(f"\nrun1 meta keys: {list(meta1.keys())}")
print(f"run1 restore_timing: {meta1.get('restore_timing', '__ABSENT')}")
trace1 = meta1.get("trace", {})
print(f"run1 trace keys: {list(trace1.keys())}")
print(f"restore in run1 trace: {'restore' in trace1}")
