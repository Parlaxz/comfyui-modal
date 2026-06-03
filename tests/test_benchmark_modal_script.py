import unittest

import benchmark_modal


class BenchmarkModalScriptUnitTests(unittest.TestCase):
    def test_classify_failure_marks_snapshot_missing_before_runs(self):
        status = benchmark_modal._classify_failure_status(
            stage="snapshot",
            exc=RuntimeError("latest benchmark workflow snapshot is empty"),
            run1_completed=False,
        )
        self.assertEqual(status, "snapshot_missing")

    def test_classify_failure_marks_health_timeout_before_run1(self):
        status = benchmark_modal._classify_failure_status(
            stage="health",
            exc=TimeoutError("local ComfyUI health timeout"),
            run1_completed=False,
        )
        self.assertEqual(status, "health_timeout")

    def test_classify_failure_marks_run1_failed_before_first_completion(self):
        status = benchmark_modal._classify_failure_status(
            stage="run1",
            exc=RuntimeError("boom"),
            run1_completed=False,
        )
        self.assertEqual(status, "run1_failed")

    def test_classify_failure_marks_run2_failed_after_first_completion(self):
        status = benchmark_modal._classify_failure_status(
            stage="run2",
            exc=RuntimeError("boom"),
            run1_completed=True,
        )
        self.assertEqual(status, "run2_failed")


if __name__ == "__main__":
    unittest.main()
