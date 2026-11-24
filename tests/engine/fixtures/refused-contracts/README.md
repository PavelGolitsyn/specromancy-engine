# Refusal specimens

Each ownership JSON object maps two paths to their original UTF-8 contents.
The manifest is intact. The matching Claude command makes replacement and stale
deletion observable with a nonempty or empty selection. Both generate and
check must exit 11 with `unsupported adapter manifest generator identity`.
Tests restore these files in temporary consumer trees.

| Specimen | Manifest / generator | Original capture under `tests/engine/fixtures/refactoring-compatibility/` |
| --- | --- | --- |
| `ownership-generator-1.json` | 1 / 1 | `v0.1.3:adapters.json`, produced at `7f8aafa` |
| `ownership-generator-2.json` | 1 / 2 | `v0.1.3:adapters-generator-v2.json` |
| `ownership-generator-3.json` | 2 / 3 | `ce5fa8a:adapters-generator-v3.json` |
| `ownership-generator-4.json` | 2 / 4 | `e218dff:adapters-generator-v4.json` |

`runs-v1.json` contains the awaiting-approval and recoverable states from
`v0.1.3:tests/engine/fixtures/refactoring-compatibility/states.json`. Both
run and event versions are 1. The original kindless approval exercises decision
refusal. The outstanding manifest revision exercises refusal before recovery.
The expected diagnostic is `unsupported-schema-version` (exit 12) and every
file must retain its bytes. Mixed logs reuse the authentic event bytes.

The retired response and full adapter captures remain in the
[Stage 27 tree](https://github.com/PavelGolitsyn/specromancy-engine/tree/e218dff/tests/engine/fixtures/refactoring-compatibility).
