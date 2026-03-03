#!/usr/bin/env python3
"""
WHOOP Experiment Tracker — define, monitor, and evaluate personal health experiments.

Usage:
  python3 experiment.py plan --name "No alcohol for 30 days" \
    --hypothesis "HRV will increase 10%+" \
    --start 2026-03-01 --end 2026-03-31 \
    --metrics hrv,recovery,sleep_performance

  python3 experiment.py list
  python3 experiment.py status --id <id>
  python3 experiment.py report --id <id>
"""

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
FETCH_SCRIPT = SCRIPT_DIR / "fetch.py"
EXPERIMENTS_FILE = Path.home() / ".openclaw/workspace/knowledge/whoop-experiments.json"

METRIC_KEYS = {
    "hrv": ("recovery", "score.hrv_rmssd_milli"),
    "recovery": ("recovery", "score.recovery_score"),
    "rhr": ("recovery", "score.resting_heart_rate"),
    "sleep_performance": ("sleep", "score.sleep_performance_percentage"),
    "strain": ("cycle", "score.strain"),
}


def load_experiments():
    EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not EXPERIMENTS_FILE.exists():
        return []
    with open(EXPERIMENTS_FILE) as f:
        return json.load(f)


def save_experiments(experiments):
    EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPERIMENTS_FILE, "w") as f:
        json.dump(experiments, f, indent=2)


def fetch_endpoint(endpoint, start, end, limit=60):
    cmd = [
        sys.executable, str(FETCH_SCRIPT), endpoint,
        "--start", start, "--end", end,
        "--limit", str(limit),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"ERROR fetching {endpoint}: {e.stderr}", file=sys.stderr)
        return {}


def deep_get(obj, path):
    """Get nested key like 'score.hrv_rmssd_milli'."""
    keys = path.split(".")
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return None
    return obj


def compute_metric_avg(endpoint, field_path, start, end):
    """Fetch data for a date range and compute average for a metric."""
    data = fetch_endpoint(f"/{endpoint}", start, end)
    records = data.get("records", [])
    values = [deep_get(r, field_path) for r in records]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def compute_baseline(metrics, start_date):
    """Compute baseline from 14 days prior to start_date."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    baseline_end = (start_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    baseline_start = (start_dt - timedelta(days=14)).strftime("%Y-%m-%d")

    print(f"Computing baseline from {baseline_start} to {baseline_end}...", file=sys.stderr)

    baseline = {}
    seen_endpoints = {}

    for metric in metrics:
        if metric not in METRIC_KEYS:
            print(f"WARNING: Unknown metric '{metric}', skipping.", file=sys.stderr)
            continue
        endpoint, field_path = METRIC_KEYS[metric]
        avg = compute_metric_avg(endpoint, field_path, baseline_start, baseline_end)
        if avg is not None:
            baseline[metric] = avg
            print(f"  {metric}: {avg}", file=sys.stderr)
        else:
            print(f"  {metric}: no data in baseline window", file=sys.stderr)

    return baseline, baseline_start, baseline_end


def compute_window_avgs(metrics, start_date, end_date):
    """Compute averages for a date window."""
    avgs = {}
    for metric in metrics:
        if metric not in METRIC_KEYS:
            continue
        endpoint, field_path = METRIC_KEYS[metric]
        avg = compute_metric_avg(endpoint, field_path, start_date, end_date)
        avgs[metric] = avg
    return avgs


def trend_arrow(delta):
    if delta is None:
        return "→"
    if delta > 0:
        return "↑"
    if delta < 0:
        return "↓"
    return "→"


def fmt_value(metric, value):
    if value is None:
        return "N/A"
    if metric in ("hrv", "rhr"):
        return f"{value:.1f}ms" if metric == "hrv" else f"{value:.0f}bpm"
    if metric in ("recovery", "sleep_performance"):
        return f"{value:.0f}%"
    return f"{value:.1f}"


def experiment_status_str(exp):
    now = datetime.now(timezone.utc).date().isoformat()
    if now < exp["start_date"]:
        return "planned"
    elif now > exp["end_date"]:
        return "completed"
    else:
        return "running"


def cmd_plan(args):
    metrics = [m.strip() for m in args.metrics.split(",")]

    # Baseline
    if args.baseline_hrv or args.baseline_recovery or args.baseline_sleep_performance or args.baseline_strain or args.baseline_rhr:
        baseline = {}
        if args.baseline_hrv:
            baseline["hrv"] = args.baseline_hrv
        if args.baseline_recovery:
            baseline["recovery"] = args.baseline_recovery
        if args.baseline_sleep_performance:
            baseline["sleep_performance"] = args.baseline_sleep_performance
        if args.baseline_strain:
            baseline["strain"] = args.baseline_strain
        if args.baseline_rhr:
            baseline["rhr"] = args.baseline_rhr
        baseline_start = baseline_end = None
    else:
        baseline, baseline_start, baseline_end = compute_baseline(metrics, args.start)

    exp = {
        "id": str(uuid.uuid4())[:8],
        "name": args.name,
        "hypothesis": args.hypothesis,
        "start_date": args.start,
        "end_date": args.end,
        "metrics": metrics,
        "baseline": baseline,
        "baseline_window": {"start": baseline_start, "end": baseline_end} if baseline_start else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": experiment_status_str({"start_date": args.start, "end_date": args.end}),
    }

    experiments = load_experiments()
    experiments.append(exp)
    save_experiments(experiments)

    print(f"\n✅ Experiment created (id: {exp['id']})")
    print(f"   Name: {exp['name']}")
    print(f"   Hypothesis: {exp['hypothesis']}")
    print(f"   Period: {exp['start_date']} → {exp['end_date']}")
    print(f"   Metrics: {', '.join(metrics)}")
    print(f"\n   Baseline:")
    for m, v in baseline.items():
        print(f"     {m}: {fmt_value(m, v)}")
    print(f"\n   Saved to: {EXPERIMENTS_FILE}")


def cmd_list(args):
    experiments = load_experiments()
    if not experiments:
        print("No experiments found.")
        return

    print(f"\n{'ID':<10} {'Status':<10} {'Name':<35} {'Period'}")
    print("-" * 80)
    for exp in experiments:
        status = experiment_status_str(exp)
        period = f"{exp['start_date']} → {exp['end_date']}"
        print(f"{exp['id']:<10} {status:<10} {exp['name'][:35]:<35} {period}")


def cmd_status(args):
    experiments = load_experiments()
    exp = next((e for e in experiments if e["id"] == args.id), None)
    if not exp:
        print(f"ERROR: No experiment with id '{args.id}'", file=sys.stderr)
        sys.exit(1)

    status = experiment_status_str(exp)
    now = datetime.now(timezone.utc).date().isoformat()
    window_end = min(now, exp["end_date"])
    window_start = exp["start_date"]

    if window_end < window_start:
        print(f"Experiment '{exp['name']}' hasn't started yet (starts {exp['start_date']}).")
        return

    print(f"\n📊 Status: {exp['name']} [{status}]")
    print(f"   Hypothesis: {exp['hypothesis']}")
    print(f"   Period: {window_start} → {exp['end_date']} (checking through {window_end})")
    print()

    print(f"   {'Metric':<20} {'Baseline':>10} {'Current':>10} {'Delta':>10} {'Change':>8}")
    print("   " + "-" * 60)

    current_avgs = compute_window_avgs(exp["metrics"], window_start, window_end)
    for metric in exp["metrics"]:
        baseline_val = exp["baseline"].get(metric)
        current_val = current_avgs.get(metric)
        if baseline_val is not None and current_val is not None:
            delta = current_val - baseline_val
            pct = (delta / baseline_val) * 100 if baseline_val != 0 else 0
            arrow = trend_arrow(delta)
            print(f"   {metric:<20} {fmt_value(metric, baseline_val):>10} {fmt_value(metric, current_val):>10} {arrow}{abs(delta):.1f:>8}   {pct:+.1f}%")
        else:
            print(f"   {metric:<20} {fmt_value(metric, baseline_val):>10} {'N/A':>10} {'':>10}")

    days_elapsed = (datetime.strptime(window_end, "%Y-%m-%d") - datetime.strptime(window_start, "%Y-%m-%d")).days
    days_total = (datetime.strptime(exp["end_date"], "%Y-%m-%d") - datetime.strptime(window_start, "%Y-%m-%d")).days
    print(f"\n   Progress: {days_elapsed}/{days_total} days")


def cmd_report(args):
    experiments = load_experiments()
    exp = next((e for e in experiments if e["id"] == args.id), None)
    if not exp:
        print(f"ERROR: No experiment with id '{args.id}'", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"WHOOP Experiment Report")
    print(f"{'='*60}")
    print(f"Name:       {exp['name']}")
    print(f"Hypothesis: {exp['hypothesis']}")
    print(f"Period:     {exp['start_date']} → {exp['end_date']}")
    print(f"Metrics:    {', '.join(exp['metrics'])}")
    print()

    print("Baseline period:", exp.get("baseline_window", {}) or "manual entry")
    print()
    print(f"{'Metric':<20} {'Baseline':>10} {'Experiment':>12} {'Change':>10}")
    print("-" * 60)

    final_avgs = compute_window_avgs(exp["metrics"], exp["start_date"], exp["end_date"])
    results = {}
    for metric in exp["metrics"]:
        baseline_val = exp["baseline"].get(metric)
        exp_val = final_avgs.get(metric)
        if baseline_val is not None and exp_val is not None:
            delta = exp_val - baseline_val
            pct = (delta / baseline_val) * 100 if baseline_val != 0 else 0
            arrow = trend_arrow(delta)
            results[metric] = {"baseline": baseline_val, "experiment": exp_val, "delta": delta, "pct": pct}
            print(f"{metric:<20} {fmt_value(metric, baseline_val):>10} {fmt_value(metric, exp_val):>12} {arrow}{pct:+.1f}%")
        else:
            results[metric] = None
            print(f"{metric:<20} {fmt_value(metric, baseline_val):>10} {'N/A':>12} {'':>10}")

    print()
    print("─" * 60)
    print("VERDICT")
    print("─" * 60)

    # Simple hypothesis evaluation heuristic
    hypothesis_lower = exp["hypothesis"].lower()
    improvements = 0
    total = 0
    for metric, res in results.items():
        if res is None:
            continue
        total += 1
        # "positive" for these metrics means higher is better
        positive_metrics = {"hrv", "recovery", "sleep_performance"}
        negative_metrics = {"rhr"}  # lower is better
        if metric in positive_metrics and res["delta"] > 0:
            improvements += 1
        elif metric in negative_metrics and res["delta"] < 0:
            improvements += 1

    if total == 0:
        verdict = "INCONCLUSIVE — No data available for comparison."
    elif improvements == total:
        verdict = "MET ✅ — All tracked metrics improved during the experiment."
    elif improvements > total / 2:
        verdict = "PARTIALLY MET 🟡 — Most metrics improved, but not all."
    elif improvements == 0:
        verdict = "NOT MET ❌ — No tracked metrics improved during the experiment."
    else:
        verdict = "INCONCLUSIVE 🤔 — Mixed results across metrics."

    print(f"\n{verdict}")
    print()
    print("Plain-language summary:")

    summaries = []
    for metric, res in results.items():
        if res is None:
            summaries.append(f"  • {metric}: insufficient data")
            continue
        direction = "improved" if res["delta"] > 0 else "declined"
        if metric in ("rhr",):
            direction = "improved" if res["delta"] < 0 else "increased"
        summaries.append(f"  • {metric}: {direction} by {abs(res['pct']):.1f}% ({fmt_value(metric, res['baseline'])} → {fmt_value(metric, res['experiment'])})")

    for s in summaries:
        print(s)

    print()
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="WHOOP Experiment Tracker")
    sub = parser.add_subparsers(dest="command")

    # plan
    plan_p = sub.add_parser("plan", help="Create a new experiment")
    plan_p.add_argument("--name", required=True)
    plan_p.add_argument("--hypothesis", required=True)
    plan_p.add_argument("--start", required=True, help="YYYY-MM-DD")
    plan_p.add_argument("--end", required=True, help="YYYY-MM-DD")
    plan_p.add_argument("--metrics", required=True, help="Comma-separated: hrv,recovery,sleep_performance,rhr,strain")
    plan_p.add_argument("--baseline-hrv", type=float)
    plan_p.add_argument("--baseline-recovery", type=float)
    plan_p.add_argument("--baseline-sleep-performance", type=float)
    plan_p.add_argument("--baseline-strain", type=float)
    plan_p.add_argument("--baseline-rhr", type=float)

    # list
    sub.add_parser("list", help="List all experiments")

    # status
    status_p = sub.add_parser("status", help="Current status of a running experiment")
    status_p.add_argument("--id", required=True)

    # report
    report_p = sub.add_parser("report", help="Final report for a completed experiment")
    report_p.add_argument("--id", required=True)

    args = parser.parse_args()

    if args.command == "plan":
        cmd_plan(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
