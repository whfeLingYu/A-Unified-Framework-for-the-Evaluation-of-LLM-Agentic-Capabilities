#!/usr/bin/env bash
set -euo pipefail

CONFIG="Config/config_MultiAgentBench/config_MultiAgentBench_research.yaml"
BACKUP="${CONFIG}.bak"
START=1
END=100

cp "$CONFIG" "$BACKUP"
trap 'cp "$BACKUP" "$CONFIG"' EXIT

for i in $(seq $START $END); do
  echo "========== Running task $i =========="

  python - <<PY
from pathlib import Path
import re

i = $i  

config_path = Path("$CONFIG")
text = config_path.read_text(encoding="utf-8")

text = re.sub(r"(^\s*start_idx:\s*)\d+", rf"\g<1>{i}", text, flags=re.M)
text = re.sub(r"(^\s*end_idx:\s*)\d+", rf"\g<1>{i}", text, flags=re.M)
text = re.sub(
    r"(^\s*agent_dir:\s*\./Agent/MultiAgentBench/research/task_)\d+(\.jsonl\s*$)",
    rf"\g<1>{i}\g<2>",
    text,
    flags=re.M,
)

config_path.write_text(text, encoding="utf-8")
print(f"Updated config for task {i}")
PY

  python main.py --config "$CONFIG"

  echo "========== Finished task $i =========="
done