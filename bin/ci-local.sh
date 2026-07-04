#!/usr/bin/env bash
# Local CI runner — mirrors GitHub Actions checks, no git/pre-commit required
# Usage: bin/ci-local.sh

set -e
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTEST="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -m pytest"

echo "============================================================"
echo "  ECC-to-Hermes Loop — Local CI"
echo "  Python: $(python3 --version)"
echo "============================================================"

echo ""
echo "=== [1/5] Phase 2: Verification Loop ==="
python3 "$BASE_DIR/phase2/verification_loop.py" --root "$BASE_DIR" 2>&1 | tail -10 || true

echo ""
echo "=== [2/5] Phase 3: Instinct Learning (dry-run) ==="
python3 "$BASE_DIR/phase3/instinct_learning.py" --dry-run 2>&1

echo ""
echo "=== [3/5] Phase 5: HUD Status ==="
python3 "$BASE_DIR/phase5/phase5.py" --json 2>&1 | grep -v "^Phase 5:" | grep -v "^  Location:" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  HUD v{d['version']} — {len(d['phases'])} phases — health={d['health']} — vigilance={d['vigilance_mode']}\")
"

echo ""
echo "=== [4/5] Phase 4: Agent Registry + Routing ==="
python3 "$BASE_DIR/phase4/phase4.py" --list 2>&1 | head -20
echo ""
echo "--- Router test ---"
python3 "$BASE_DIR/phase4/phase4.py" --agent planner --task "plan auth system" 2>&1 | grep -E "Routing|Skill:|Role:|Task:|DRY"

echo ""
echo "=== [5/5] Phase 6: Evaluator RAG ==="
TEMP_STATE=$(mktemp)
python3 "$BASE_DIR/phase5/phase5.py" --json 2>/dev/null > "$TEMP_STATE"
python3 "$BASE_DIR/phase6/phase6.py" --state "$TEMP_STATE" --query "ECC self-improvement" 2>&1
rm -f "$TEMP_STATE"

echo ""
echo "=== [6/6] Run all tests ==="
cd "$BASE_DIR"
$PYTEST --tb=short -q 2>&1

echo ""
echo "============================================================"
echo "  Local CI complete"
echo "============================================================"
