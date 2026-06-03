# OpenCode "deepseek v4 flash" Preset Design

## Summary

Add a new oh-my-opencode-slim preset called `"deepseek v4 flash"` that uses the
`deepseek/deepseek-v4-flash` model from the native deepseek provider for every
role. No `council` block within the preset.

## Motivation

The user wants a test profile that exclusively uses deepseek's own hosted
`deepseek-v4-flash` (via the `deepseek/` prefix), without any opencode-go or
openai fallbacks, and without a council sub-agent.

## Preset Structure

```json
"deepseek v4 flash": {
  "orchestrator": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "max",
    "skills": ["*"],
    "mcps": ["*", "!context7"]
  },
  "oracle": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "max",
    "skills": ["simplify"],
    "mcps": []
  },
  "librarian": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "low",
    "skills": [],
    "mcps": ["websearch", "context7", "grep_app"]
  },
  "explorer": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "low",
    "skills": [],
    "mcps": []
  },
  "designer": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "medium",
    "skills": ["agent-browser"],
    "mcps": []
  },
  "fixer": {
    "model": "deepseek/deepseek-v4-flash",
    "variant": "low",
    "skills": [],
    "mcps": []
  }
}
```

Note: `council` is intentionally omitted from this preset.

## Scope

Single-file change to `C:\Users\parla\.config\opencode\oh-my-opencode-slim.json`.
No other files affected.

## Risks

None. Adding a new preset is additive and doesn't alter existing presets or the
active preset selection.
