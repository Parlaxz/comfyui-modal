"""Direct test: call Modal run_prompt and check _restore_timing in the raw response."""
import asyncio
import json
import sys
import os

# Add the custom node dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modal_client import _api


async def main():
    api = _api()
    
    # Use remote to call the deployed Modal method
    # We need to find the right function reference
    # run_prompt is a method of ComfyAPI class
    # The deployed app has it as api.run_prompt
    
    # First, let's just print what's available
    print("api attributes:", [x for x in dir(api) if not x.startswith('_')])
    
    # Try calling run_prompt with a minimal workflow that won't execute
    # but should still exercise the code path
    try:
        # Minimal valid invocation - just returns what we need
        result = await asyncio.to_thread(
            lambda: api.run_prompt.remote(
                {"__test__": True},
                {},
                {"__test_trace__": True}
            )
        )
        print("=== Result type:", type(result).__name__)
        if isinstance(result, dict):
            print("=== Result keys:", list(result.keys()))
            rt = result.get("_restore_timing", "__NOT_FOUND__")
            print("=== _restore_timing:", rt)
            trace = result.get("trace", {})
            if isinstance(trace, dict):
                print("=== trace keys:", list(trace.keys()))
                print("=== restore in trace:", trace.get("restore", "__NOT_FOUND__"))
            else:
                print("=== trace type:", type(trace).__name__, "value:", trace)
        else:
            print("=== Full result:", str(result)[:500])
    except Exception as e:
        print(f"=== Error (expected): {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
