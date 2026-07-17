#!/usr/bin/env bash
# Run the entire Hermes producer-brain test suite. ZERO money is spent:
#   - pricing/gate engine     -> deterministic, offline (PRODUCER_COST_STUB)
#   - orchestrated judgment    -> mock generation + real free edge-tts + real ffmpeg
#   - live Nemotron judgment   -> FREE nvidia/nemotron-3-super-120b-a12b (needs NVIDIA_API_KEY)
#
# Usage:  ./run_all_tests.sh            # engine + orchestrator + (eval if key present)
#         ./run_all_tests.sh --no-eval  # skip the live Nemotron eval
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
# Deterministic planning prices for the engine + orchestrator tests.
export PRODUCER_COST_STUB='{"seedance_2_0": 22, "gpt_image_2": 7, "nano_banana_flash": 4, "__default__": 10}'

fail=0

echo "================================================================"
echo " 1. ENGINE — producer.py pricing + budget gate (deterministic)"
echo "================================================================"
python3 -m unittest tests.test_producer -v || fail=1

echo
echo "================================================================"
echo " 2. ORCHESTRATOR — judgment calls end to end (mock, \$0)"
echo "    approve / downgrade / decline money-shot / VO-over-budget"
echo "================================================================"
python3 -m unittest tests.test_orchestrator -v || fail=1

echo
echo "================================================================"
echo " 2b. NEW UNITS — higgsfield parse / cinematic prompt / card copy"
echo "     / budget bridge / post-pay failure handler (mock, \$0)"
echo "================================================================"
python3 -m unittest tests.test_adapters_higgsfield_parse -v   || fail=1
python3 -m unittest tests.test_adapters_cinematic_prompt -v   || fail=1
python3 -m unittest tests.test_remotion_codegen_cardcopy -v   || fail=1
python3 -m unittest tests.test_orchestrator_budget_bridge -v  || fail=1
python3 -m unittest tests.test_build_runner_failure -v        || fail=1
python3 -m unittest tests.test_orchestrator_parallel -v       || fail=1
python3 -m unittest tests.test_adapters_stitch_mixed_res -v   || fail=1
python3 -m unittest tests.test_build_timeline -v              || fail=1
python3 -m unittest tests.test_brand_extract -v               || fail=1
python3 -m unittest tests.test_paas_branding -v               || fail=1
python3 -m unittest tests.test_night_look -v                 || fail=1
python3 -m unittest tests.test_plan_guards -v                 || fail=1
python3 -m unittest tests.test_style_fill -v                  || fail=1
python3 -m unittest tests.test_pricing -v                     || fail=1
python3 -m unittest tests.test_analytics -v                   || fail=1

echo
echo "================================================================"
echo " 2c. STRIPE EARN — checkout helper param shape + TEST-key guard"
echo "     (script, not unittest — invoked by path; offline, \$0)"
echo "================================================================"
python3 tests/test_stripe_earn.py || fail=1

if [ "${1:-}" != "--no-eval" ]; then
  echo
  echo "================================================================"
  echo " 3. LIVE BRAIN — does Nemotron pick the right verdict? (FREE)"
  echo "================================================================"
  # shellcheck disable=SC1090
  source ~/.zshrc 2>/dev/null || true
  if [ -n "${NVIDIA_API_KEY:-}" ]; then
    python3 hermes_judgment_eval.py || fail=1
  else
    echo "  SKIPPED — NVIDIA_API_KEY not in env (run: source ~/.zshrc)."
  fi

  echo
  echo "================================================================"
  echo " 4. SKILL ROUTING — can the small model drive Hermes's skills? (FREE)"
  echo "================================================================"
  if [ -n "${NVIDIA_API_KEY:-}" ]; then
    python3 hermes_skill_eval.py || fail=1
  else
    echo "  SKIPPED — NVIDIA_API_KEY not in env."
  fi
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "ALL TESTS PASSED — \$0 spent."
else
  echo "SOME TESTS FAILED (see above)."
fi
exit "$fail"
