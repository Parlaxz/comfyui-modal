from __future__ import annotations
import json
from pathlib import Path
from dual_transport_carryover_analysis import analyze

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "artifacts" / "phase_p1_parallel_golden_v1"
NEW = ROOT / "artifacts" / "dual_transport_carryover_20260916" / "new20"
OLD_COHORTS = (
    "2026-09-16_22-34-41_7f0dcf", "2026-09-16_22-36-42_ea8709",
    "2026-09-16_22-41-42_27f3cf", "2026-09-16_22-42-43_2a3bac",
    "2026-09-16_22-43-51_5a3f55", "2026-09-16_22-44-49_02c907",
    "2026-09-16_22-47-24_70c0f8", "2026-09-16_22-48-26_01e2de",
    "2026-09-16_22-49-30_c7da28", "2026-09-16_22-51-07_95283a",
    "2026-09-16_22-52-36_98ff6c", "2026-09-16_22-53-31_8919bf",
    "2026-09-16_22-54-45_18e835", "2026-09-16_22-55-50_86b475",
    "2026-09-16_22-56-53_ddbbf8", "2026-09-16_22-58-07_c99492",
    "2026-09-16_22-59-04_f4138a", "2026-09-16_23-00-02_84a1b8",
    "2026-09-16_23-01-35_6fd55b", "2026-09-16_23-02-38_21de85",
)

def decision_paths(arm: str) -> list[Path]:
    return [NEW / arm / f"attempt_{index:03d}.decision.json" for index in range(1, 21)]

def rows_from_decisions(arm: str) -> list[dict]:
    rows = []
    for decision_path in decision_paths(arm):
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        if not decision.get("valid"):
            raise RuntimeError(f"selected new request is invalid: {decision_path}: {decision}")
        rows.append(analyze(Path(decision["run_artifact"])))
    return rows

def old_rows() -> list[dict]:
    return [analyze(RAW / cohort / "attempt_0.json") for cohort in OLD_COHORTS]

def valid(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["output_valid"] and row["true_cold"] and row["dual_identity_valid"]]

def summary(rows: list[dict]) -> dict:
    result = {}
    for arm in ("sham", "split"):
        subset = [row for row in valid(rows) if row["arm"] == arm]
        sick = [row for row in subset if row["hard_sick_clip"]]
        result[arm] = {
            "valid_count": len(subset),
            "hard_sick_clip_count": len(sick),
            "hard_sick_unet_given_hard_sick_clip_count": sum(row["hard_sick_unet"] for row in sick),
            "hard_sick_unet_given_hard_sick_clip_rate": (sum(row["hard_sick_unet"] for row in sick) / len(sick)) if sick else None,
            "hard_sick_clip_rows": [
                {"request": row["request"], "unet_load_ms": row["unet"]["load_ms"], "unet_max_preadv_ms": row["unet"]["max_preadv_ms"], "hard_sick_unet": row["hard_sick_unet"]}
                for row in sick
            ],
        }
    return result

def main() -> None:
    old = old_rows()
    new = rows_from_decisions("sham") + rows_from_decisions("split")
    combined = old + new
    payload = {"old_10_per_arm": {"rows": old, "summary": summary(old)}, "new_20_per_arm": {"rows": new, "summary": summary(new)}, "combined_30_per_arm": {"rows": combined, "summary": summary(combined)}}
    out_dir = ROOT / "artifacts" / "dual_transport_carryover_20260916"
    (out_dir / "analysis_new20_and_combined.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = ["# Dual-transport additional cohort analysis", "", "## Summary", "", "| cohort | arm | valid | HARD_SICK_CLIP | HARD_SICK_UNET among hard-sick CLIP | rate |", "|---|---|---:|---:|---:|---:|"]
    for cohort, data in payload.items():
        for arm, item in data["summary"].items():
            rate = "n/a" if item["hard_sick_unet_given_hard_sick_clip_rate"] is None else f"{item['hard_sick_unet_given_hard_sick_clip_rate']:.3f}"
            lines.append(f"| {cohort} | {arm} | {item['valid_count']} | {item['hard_sick_clip_count']} | {item['hard_sick_unet_given_hard_sick_clip_count']} | {rate} |")
    lines += ["", "## Hard-sick CLIP continuous UNET timings", "", "| cohort | arm | request | UNET load ms | UNET max preadv ms | HARD_SICK_UNET |", "|---|---|---|---:|---:|---|"]
    for cohort, data in payload.items():
        for arm, item in data["summary"].items():
            for row in item["hard_sick_clip_rows"]:
                lines.append(f"| {cohort} | {arm} | {row['request']} | {row['unet_load_ms']:.3f} | {row['unet_max_preadv_ms']:.3f} | {row['hard_sick_unet']} |")
    lines += ["", "## Full row data", "", "The JSON artifact contains the complete row table, including all descriptive CLIP/UNET timings and preadv threshold counts."]
    (out_dir / "analysis_new20_and_combined.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({cohort: data["summary"] for cohort, data in payload.items()}, indent=2))

if __name__ == "__main__":
    main()
