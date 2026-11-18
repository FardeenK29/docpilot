#!/usr/bin/env bash
# Run teardown presets back to back under the same conditions.
# Models are unloaded between presets so each starts cold, then warms up.
#   evals/run_all.sh                      # every preset
#   evals/run_all.sh step2_gate optimized # just these
set -euo pipefail
cd "$(dirname "$0")/.."
presets=("$@")
[ ${#presets[@]} -eq 0 ] && presets=(baseline step1_ctx step2_router step2_gate optimized)
for preset in "${presets[@]}"; do
  for m in qwen2.5:3b qwen2.5:1.5b; do ollama stop "$m" >/dev/null 2>&1 || true; done
  rm -f data/tickets.jsonl
  echo "=== $preset $(date +%H:%M:%S)"
  .venv/bin/python -m evals.run_eval --preset "$preset" > "results/$preset.log" 2>&1
done
.venv/bin/python -m evals.compare baseline step1_ctx step2_router step2_gate optimized
