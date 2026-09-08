For structural code questions—symbols, callers/callees, architecture, cross-file impact, and dead-code analysis—prefer Codebase Memory graph discovery first, then verify exact source and coverage gaps with native tools. Native Read/Grep/Glob remain allowed for verification.

Never use raw modal deploy, modal app history, or equivalent for this repository. Use v2ctl; destination is config-owned.

## Test-performance policy

- Ordinary development uses the FAST_UNIT verification path.
- HEAVY_LOCAL tests are explicitly selected only when heavyweight runtime or lifecycle coverage is needed.
- A supposedly lightweight test taking more than 10 seconds is a diagnostic failure. After one unexpected lightweight-test timeout, stop and diagnose collection, import, setup, call, and teardown phases rather than retrying with a larger timeout.
- Use `tools/test_perf.py` for bounded slow-test diagnosis. Do not skip, delete, or weaken tests because they are slow.
- Never escalate `60s -> 120s -> 300s` without new evidence.
- Heavyweight runtime tests remain valid, but must not contaminate ordinary FAST_UNIT verification.

Canonical local commands:

```text
FAST verification:
python tools/test_perf.py --fast -- tests -m fast_unit

HEAVY_LOCAL verification:
python -m pytest tests -m heavy_local

slow-test diagnosis:
python tools/test_perf.py --fast --timeout 15 --budget 10 -- tests/test_file.py::test_name
```
