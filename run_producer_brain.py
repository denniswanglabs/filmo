#!/usr/bin/env python3
"""Run the producer-brain job by directly calling the walk-studio MCP tools."""

import os
import sys
import json

# Add the project directory to path
HERE = "/Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent"
sys.path.insert(0, HERE)

# Load environment variables
for env_path in [os.path.expanduser("~/.hermes/.env"), os.path.join(HERE, ".env")]:
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass

# Now import the mcp_studio_server module
import mcp_studio_server as mcp

def call_tool(name, args):
    """Call a tool and print the result."""
    print(f"\n{'='*60}")
    print(f"CALLING: {name}")
    print(f"ARGS: {json.dumps(args, indent=2)}")
    print(f"{'='*60}")
    
    handler = mcp.TOOLS[name]["handler"]
    result = handler(args)
    
    print(f"RESULT:")
    print(json.dumps(result, indent=2, default=str))
    
    if not result.get("ok"):
        print(f"\n❌ TOOL FAILED: {result.get('error')}")
        sys.exit(1)
    
    return result

def main():
    # Step 1: conversion_read with Nemotron Ultra (brain="ultra-paid")
    print("\n🔍 STEP 1: Conversion Read (Nemotron Ultra)")
    read_result = call_tool("conversion_read", {
        "url": "https://stripe.com",
        "brain": "ultra-paid"
    })
    
    # Step 2: plan_job with Nemotron Ultra (brain="ultra-paid")
    print("\n📋 STEP 2: Plan Job (Nemotron Ultra)")
    plan_result = call_tool("plan_job", {
        "url": "https://stripe.com",
        "goal": "Show Stripe as the unified platform to grow revenue",
        "duration": 30,
        "brain": "ultra-paid"
    })
    plan_path = plan_result["plan_path"]
    print(f"\n✅ Plan saved to: {plan_path}")
    
    # Step 3: price_job
    print("\n💰 STEP 3: Price Job")
    price_result = call_tool("price_job", {
        "plan_path": plan_path
    })
    
    # Parse the estimate to get suggested price
    estimate_raw = price_result.get("estimate_raw", "")
    print(f"Estimate output: {estimate_raw}")
    
    # Extract suggested price from the output
    import re
    price_match = re.search(r"suggested_price_cents:\s*(\d+)", estimate_raw)
    if not price_match:
        price_match = re.search(r"Suggested price.*?(\d+)\s*cents", estimate_raw, re.IGNORECASE)
    if not price_match:
        price_match = re.search(r"price_cents.*?(\d+)", estimate_raw)
    
    if price_match:
        suggested_price_cents = int(price_match.group(1))
    else:
        # Fallback: try to parse JSON from stdout
        try:
            # The producer.py estimate might output JSON
            estimate_data = json.loads(estimate_raw)
            suggested_price_cents = estimate_data.get("suggested_price_cents", 0)
        except:
            suggested_price_cents = 5000  # $50 fallback
    
    print(f"\n💵 Suggested price: {suggested_price_cents} cents (${suggested_price_cents/100:.2f})")
    
    # Step 4: earn_stripe
    print("\n💳 STEP 4: Earn Stripe (TEST MODE)")
    earn_result = call_tool("earn_stripe", {
        "plan_path": plan_path,
        "price_cents": suggested_price_cents
    })
    
    # Check for live key refusal
    if earn_result.get("key_kind") == "live":
        print("\n❌ LIVE KEY DETECTED - STOPPING")
        sys.exit(1)

    # Step 4.5: simulate the customer paying the link with the 4242 test card.
    # Closes the earn loop (link -> paid) with a REAL test-mode succeeded payment.
    print("\n💸 STEP 4.5: Simulate customer payment (Stripe 4242 test card)")
    pay_result = call_tool("simulate_payment", {
        "plan_path": plan_path,
        "price_cents": suggested_price_cents,
        "payment_link_id": earn_result.get("earn", {}).get("payment_link_id"),
    })
    if pay_result.get("paid"):
        print(f"   ✅ Paid ${(pay_result.get('amount_received_cents') or 0)/100:.2f} "
              f"via {pay_result.get('card_brand')} ****{pay_result.get('card_last4')} "
              f"(PaymentIntent {pay_result.get('payment_intent_id')}, test mode)")
    else:
        print(f"   ⚠️  payment not confirmed: {pay_result.get('status')} {pay_result.get('error','')}")

    # Step 5+6: Budget gate and produce each scene
    print("\n🎬 STEP 5+6: Budget Gate + Produce Scenes")
    
    # Load the plan to get scenes
    with open(plan_path, "r") as f:
        plan = json.load(f)
    
    scenes = plan.get("scenes", [])
    spent_cents = 0
    gate_outcomes = []
    
    for scene in scenes:
        scene_id = scene["id"]
        scene_type = scene["type"]
        duration = scene.get("duration_s", 5)
        
        print(f"\n--- Scene: {scene_id} ({scene_type}, {duration}s) ---")
        
        # For free scenes, proposed cost is 0
        if scene_type in ("title", "motion_graphic", "walkthrough"):
            proposed = 0
        else:
            # For cinematic scenes, we need to get the proposed cost from the plan
            proposed = scene.get("estimated_cost_cents", 500)  # fallback
        
        # Budget gate
        gate_result = call_tool("budget_gate", {
            "plan_path": plan_path,
            "scene_id": scene_id,
            "proposed_cost_cents": proposed,
            "spent_cents": spent_cents
        })
        
        # Parse verdict
        verdict_raw = gate_result.get("verdict_raw", "")
        verdict = "approve"  # default
        if "decline" in verdict_raw.lower():
            verdict = "decline"
        elif "downgrade" in verdict_raw.lower():
            verdict = "downgrade"
        elif "approve" in verdict_raw.lower():
            verdict = "approve"
        
        gate_outcomes.append({
            "scene_id": scene_id,
            "scene_type": scene_type,
            "proposed_cost_cents": proposed,
            "verdict": verdict,
            "spent_before_cents": spent_cents
        })
        
        print(f"Gate verdict: {verdict}")
        
        if verdict == "decline":
            print(f"⚠️  Scene {scene_id} DECLINED - skipping production")
            continue
        
        # Produce scene (REAL / POLISHED mode)
        produce_result = call_tool("produce_scene", {
            "plan_path": plan_path,
            "scene_id": scene_id,
            "real": True
        })
        
        if verdict == "approve":
            spent_cents += proposed
        elif verdict == "downgrade":
            # Use downgraded cost if available
            spent_cents += proposed  # simplified
        
        print(f"Running spend: {spent_cents} cents")
    
    # Step 7: synthesize_vo with ElevenLabs
    print("\n🎙️ STEP 7: Synthesize VO (ElevenLabs)")
    vo_result = call_tool("synthesize_vo", {
        "plan_path": plan_path,
        "provider": "elevenlabs"
    })
    
    # Step 8: stitch_final (REAL / POLISHED mode)
    print("\n🎞️ STEP 8: Stitch Final (REAL / POLISHED)")
    stitch_result = call_tool("stitch_final", {
        "plan_path": plan_path,
        "real": True
    })
    
    final_path = stitch_result.get("output_path")
    final_duration = stitch_result.get("duration_s")
    
    # Final P&L Report
    print("\n" + "="*60)
    print("📊 FINAL P&L REPORT")
    print("="*60)
    
    print(f"\n🎬 Final Video: {final_path}")
    print(f"⏱️  Duration: {final_duration}s")
    print(f"💰 Price Charged: ${suggested_price_cents/100:.2f} ({suggested_price_cents} cents)")
    
    actual_cogs = 0
    for outcome in gate_outcomes:
        status = "✅" if outcome["verdict"] == "approve" else "⬇️" if outcome["verdict"] == "downgrade" else "❌"
        cost = outcome["proposed_cost_cents"] if outcome["verdict"] != "decline" else 0
        actual_cogs += cost
        print(f"  {status} {outcome['scene_id']} ({outcome['scene_type']}): {outcome['verdict'].upper()} - ${cost/100:.2f}")
    
    # VO cost
    vo_cost = 0
    if vo_result.get("paid"):
        vo_cost = 100  # estimate
        print(f"  🎙️ Voiceover (ElevenLabs): ${vo_cost/100:.2f}")
        actual_cogs += vo_cost
    
    margin = (suggested_price_cents - actual_cogs) / suggested_price_cents if suggested_price_cents > 0 else 0
    
    print(f"\n📈 Actual COGS: ${actual_cogs/100:.2f} ({actual_cogs} cents)")
    print(f"📊 Margin: {margin*100:.1f}%")
    print(f"💵 Net Profit: ${(suggested_price_cents - actual_cogs)/100:.2f}")
    
    print("\n🧠 Nemotron Ultra Usage:")
    print("  • Conversion Read: Nemotron Ultra (brain='ultra-paid')")
    print("  • Plan Job: Nemotron Ultra (brain='ultra-paid')")
    print("  • Budget Gate judgments: Nemotron Ultra (via producer-brain skill)")
    
    print("\n✅ JOB COMPLETE")

if __name__ == "__main__":
    main()