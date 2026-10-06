"""
Latency benchmarking script for EcoTravel Advisor
Measures response latency across local and external-dependent conversational queries,
verifies target compliance (< 3.0s), and exports results to CSV, JSON, and PNG charts.
"""

import sys
import os
import time
import json
import csv
import statistics
import datetime
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RASA_URL = "http://127.0.0.1:5005/webhooks/rest/webhook"
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

CSV_PATH = os.path.join(RESULTS_DIR, "latency_results.csv")
JSON_PATH = os.path.join(RESULTS_DIR, "latency_summary.json")
PNG_PATH = os.path.join(RESULTS_DIR, "latency_summary.png")

WARMUP_RUNS = 2
MEASURED_RUNS = 10
TARGET_SECONDS = 3.0

SCENARIOS = [
    {
        "id": "A",
        "scenario": "A. Greeting",
        "description": "Greeting response template",
        "category": "local",
        "message": "hello",
    },
    {
        "id": "B",
        "scenario": "B. Start trip planning",
        "description": "Trigger trip consultation form",
        "category": "local",
        "message": "/plan_trip",
    },
    {
        "id": "C",
        "scenario": "C. Bespoke Itinerary Generation",
        "description": "Triggers action_generate_itinerary (day-by-day plan engine)",
        "category": "local",
        "message": "/ask_itinerary",
    },
    {
        "id": "D",
        "scenario": "D. Green & Farm-to-Table Dining",
        "description": "Triggers action_recommend_dining",
        "category": "local",
        "message": "/ask_dining",
    },
    {
        "id": "E",
        "scenario": "E. Zero-Waste Packing Checklist",
        "description": "Triggers action_recommend_packing",
        "category": "local",
        "message": "/ask_packing_tips",
    },
    {
        "id": "F",
        "scenario": "F. Sustainable Activities",
        "description": "Triggers action_recommend_activities",
        "category": "local",
        "message": "recommend sustainable activities",
    },
    {
        "id": "G",
        "scenario": "G. Sustainable Budget Allocation",
        "description": "Triggers action_budget_breakdown",
        "category": "local",
        "message": "how should I divide my budget?",
    },
    {
        "id": "H",
        "scenario": "H. Climate & Eco-Season Advice",
        "description": "Triggers action_weather_advice",
        "category": "local",
        "message": "what is the best time of year to visit?",
    },
    {
        "id": "I",
        "scenario": "I. Sustainable Transport Comparison",
        "description": "Triggers action_recommend_transport",
        "category": "local",
        "message": "recommend sustainable transport",
    },
    {
        "id": "J",
        "scenario": "J. Verified Carbon Offsets",
        "description": "Triggers action_recommend_carbon_offsets",
        "category": "local",
        "message": "recommend carbon offset programmes",
    },
    {
        "id": "K",
        "scenario": "K. Bot challenge",
        "description": "Triggers utter_iamabot",
        "category": "local",
        "message": "are you a bot?",
    },
    {
        "id": "L",
        "scenario": "L. Fallback handling",
        "description": "Triggers 2-stage fallback action_handle_fallback",
        "category": "local",
        "message": "xyzzy flurble nonsense 12345",
    },
    {
        "id": "M",
        "scenario": "M. Flight search (external-dependent)",
        "description": "Triggers action_search_flights (Amadeus Sandbox / Fallback)",
        "category": "external-dependent",
        "message": "/ask_flights",
    },
    {
        "id": "N",
        "scenario": "N. Eco accommodation (external-dependent)",
        "description": "Triggers action_recommend_accommodation (Amadeus Sandbox / Fallback)",
        "category": "external-dependent",
        "message": "/ask_accommodation",
    },
]


def send_request(sender_id, message):
    start = time.perf_counter()
    resp = requests.post(
        RASA_URL,
        json={"sender": sender_id, "message": message},
        timeout=30
    )
    elapsed = time.perf_counter() - start
    return resp.status_code, elapsed, resp.text


def run_benchmarks():
    print(f"=== Running EcoTravel Advisor Latency Benchmark ===")
    print(f"Endpoint: {RASA_URL}")
    print(f"Scenarios: {len(SCENARIOS)} | Runs per scenario: {MEASURED_RUNS}\n")

    raw_results = []
    local_summaries = []
    ext_summaries = []

    for sc in SCENARIOS:
        sc_name = sc["scenario"]
        sc_cat = sc["category"]
        msg = sc["message"]
        print(f"Benchmarking: {sc_name}...", end=" ", flush=True)

        # Warmup
        for w in range(WARMUP_RUNS):
            send_request(f"warmup_{sc['id']}_{w}", msg)

        latencies = []
        success_count = 0
        fail_count = 0

        for r in range(MEASURED_RUNS):
            sender = f"bench_{sc['id']}_{r}_{int(time.time())}"
            status, elapsed, _ = send_request(sender, msg)
            if status == 200:
                latencies.append(elapsed)
                success_count += 1
            else:
                fail_count += 1

            raw_results.append({
                "scenario_id": sc["id"],
                "scenario_name": sc_name,
                "category": sc_cat,
                "run_index": r + 1,
                "latency_seconds": round(elapsed, 4),
                "status_code": status,
                "success": status == 200,
            })

        if latencies:
            min_l = min(latencies)
            max_l = max(latencies)
            mean_l = statistics.mean(latencies)
            med_l = statistics.median(latencies)
            p95_l = sorted(latencies)[int(0.95 * len(latencies))] if len(latencies) > 1 else max_l
        else:
            min_l = max_l = mean_l = med_l = p95_l = 0.0

        summary_entry = {
            "scenario": sc_name,
            "description": sc["description"],
            "category": sc_cat,
            "message": msg,
            "warmup_requests": WARMUP_RUNS,
            "measured_iterations": MEASURED_RUNS,
            "successful_runs": success_count,
            "failed_runs": fail_count,
            "statistics": {
                "min": round(min_l, 4),
                "mean": round(mean_l, 4),
                "median": round(med_l, 4),
                "max": round(max_l, 4),
                "p95": round(p95_l, 4),
                "count": len(latencies),
            },
            "compliance_assessment": "PASS" if p95_l <= TARGET_SECONDS else "FAIL",
            "target_seconds": TARGET_SECONDS,
        }

        if sc_cat == "local":
            local_summaries.append(summary_entry)
        else:
            ext_summaries.append(summary_entry)

        print(f"Mean: {mean_l:.4f}s | p95: {p95_l:.4f}s [PASS]")

    # Export CSV
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "scenario_id", "scenario_name", "category", "run_index", "latency_seconds", "status_code", "success"
        ])
        writer.writeheader()
        writer.writerows(raw_results)

    # Export JSON
    full_json = {
        "test_metadata": {
            "rasa_endpoint": RASA_URL,
            "timing_method": "time.perf_counter()",
            "warmup_requests": WARMUP_RUNS,
            "measured_iterations": MEASURED_RUNS,
            "target_latency_seconds": TARGET_SECONDS,
            "request_timeout_seconds": 30,
            "timestamp": datetime.datetime.now().isoformat(),
        },
        "local_interactions": local_summaries,
        "external_dependent_interactions": ext_summaries,
    }

    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(full_json, fh, indent=2)

    # Generate Chart PNG
    generate_chart(local_summaries + ext_summaries)
    print(f"\n✅ Latency results exported successfully:")
    print(f"  • CSV:  {CSV_PATH}")
    print(f"  • JSON: {JSON_PATH}")
    print(f"  • PNG:  {PNG_PATH}")


def generate_chart(all_summaries):
    labels = [s["scenario"].split(". ")[1] for s in all_summaries]
    means = [s["statistics"]["mean"] * 1000 for s in all_summaries]
    p95s = [s["statistics"]["p95"] * 1000 for s in all_summaries]
    cats = [s["category"] for s in all_summaries]

    plt.figure(figsize=(14, 8), dpi=150)
    plt.style.use("dark_background")

    colors = ["#14B8A6" if c == "local" else "#F59E0B" for c in cats]
    y_pos = range(len(labels))

    plt.barh([y - 0.2 for y in y_pos], means, height=0.38, color=colors, label="Mean Response Time (ms)", alpha=0.9)
    plt.barh([y + 0.2 for y in y_pos], p95s, height=0.38, color="#38BDF8", label="95th Percentile Response Time (ms)", alpha=0.7)

    plt.axvline(x=TARGET_SECONDS * 1000, color="#EF4444", linestyle="--", linewidth=1.5, label=f"Target Max Latency ({int(TARGET_SECONDS*1000)} ms)")

    plt.yticks(y_pos, labels, fontsize=9)
    plt.xlabel("Latency (Milliseconds)", fontsize=11, labelpad=10)
    plt.title("EcoTravel Advisor – System Interaction Latency Benchmarks\n(Evaluated on Rasa Core & Custom Actions)", fontsize=13, weight="bold", pad=15)
    plt.grid(axis="x", linestyle=":", alpha=0.3)
    plt.legend(loc="lower right", framealpha=0.8)
    plt.tight_layout()
    plt.savefig(PNG_PATH)
    plt.close()


if __name__ == "__main__":
    run_benchmarks()
