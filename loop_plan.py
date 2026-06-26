#!/usr/bin/env python3
"""LOOP plan engine: analyze + brand + plan ONLY (stops before the local VO hang).
Writes runs/<id>/plan.json (+ brand_theme.json + conversion_read.json) so the loop
can iterate on the BRAIN prompts (planner-prompt.md / analyze) and re-measure with
loop_measure.py. Usage: python3 loop_plan.py <url> <goal> <run-id>"""
import json, os, sys
import build_runner as br, plan_job

url, goal, run_id = sys.argv[1], sys.argv[2], sys.argv[3]
run_dir = os.path.join("runs", run_id)
os.makedirs(run_dir, exist_ok=True)

# 1) Conversion Read (Nemotron via ANALYZE_BRAIN) — text read; site capture is
#    best-effort and absent locally (fine).
cr = br._maybe_conversion_read(url, run_dir, brain=br.ANALYZE_BRAIN)
# 2) Brand theme + facts (writes brand_theme.json).
brand_path = br._resolve_brand_theme(url, run_dir)
facts = br._brand_facts(url, run_dir)
# 3) Plan (Nemotron 550B planner).
plan = plan_job.plan_job(url, goal, 30, style="snappy", quality="standard",
                         brain="ultra-paid", conversion_read=cr)
plan_path = os.path.join(run_dir, "plan.json")
json.dump(plan, open(plan_path, "w"), indent=2)
print("PLAN:", os.path.abspath(plan_path))
print("BRAND:", brand_path)
print("SCENE_TYPES:", [s.get("type") for s in (plan.get("scenes") or [])])
