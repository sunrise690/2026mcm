"""Cloud-side staged search for adaptive Q3 route topology parameters."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "repro"
CONFIGS = ROOT / "configs"
RUNNER = ROOT / "src" / "run_local.py"
BASE_NAME = "alg_topoadapt_k10_r75"
STATE = ROOT / "reports" / "topoadapt_search_state.json"
SIM = ROOT / "sources" / "jammers_offline_sim_v3" / "jammers_offline_sim.py"

PARAMS = {
    "route_batch_lock_min_known": (8, 13, "int"),
    "route_batch_lock_min_items": (2, 5, "int"),
    "route_batch_adaptive_regret_m": (20.0, 220.0, "float"),
    "route_batch_insert_max_detour_m": (350.0, 2400.0, "float"),
    "dynamic_route_discovery_value_s": (35.0, 220.0, "float"),
    "dynamic_route_max_known": (6, 12, "int"),
    "direct_probe_max_detour_m": (300.0, 900.0, "float"),
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_sim():
    spec = importlib.util.spec_from_file_location("q3_search_sim", SIM)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def seed_bytes(seed: int):
    return hashlib.sha256(f"cumcm-offline-generator-key:{seed}".encode()).digest()


def balanced_seeds(start: int, per_n: int):
    sim = load_sim()
    groups = {n: [] for n in range(10, 17)}
    seed = start
    while min(map(len, groups.values())) < per_n:
        n = len(sim.generate_practice(3, seed_bytes(seed)).jammers)
        if n in groups and len(groups[n]) < per_n:
            groups[n].append(seed)
        seed += 1
    return groups, [seed for n in range(10, 17) for seed in groups[n]]


def clamp_value(key: str, value):
    lo, hi, kind = PARAMS[key]
    value = max(lo, min(hi, value))
    return int(round(value)) if kind == "int" else round(float(value), 3)


def sample_tune(rng: random.Random, center: dict, scale: float):
    tune = copy.deepcopy(center)
    for key, (lo, hi, kind) in PARAMS.items():
        span = hi - lo
        value = float(center[key]) + rng.gauss(0.0, span * scale)
        tune[key] = clamp_value(key, value)
    tune["route_batch_lock_enabled"] = 1
    return tune


def write_candidates(round_no: int, center: dict, population: int, rng: random.Random):
    names = []
    scale = max(0.045, 0.24 * (0.68 ** (round_no - 1)))
    for index in range(population):
        name = f"topoadapt_r{round_no:02d}_{index:02d}"
        tune = copy.deepcopy(center) if index == 0 else sample_tune(rng, center, scale)
        save_json(CONFIGS / f"{name}.json", {"controller": "tunable", "tune": tune})
        names.append(name)
    return names, scale


def evaluate(names: list[str], seeds: list[int], workers: int, label: str):
    cmd = [sys.executable, "-B", str(RUNNER), "--variants", ",".join(names),
           "--seeds", ",".join(map(str, seeds)), "--workers", str(workers),
           "--timeout", "120", "--label", label]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="", flush=True)
    if proc.returncode:
        raise RuntimeError(f"evaluation failed: {proc.returncode}")
    match = re.search(r"^RUN_DIR=(.+)$", proc.stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("RUN_DIR missing")
    result = load_json(Path(match.group(1).strip()) / "results.json")
    return result, {row["variant"]: row for row in result["summary"]}


def rank_key(summary: dict):
    fullclear = int(summary["fullclear_runs"] == summary["runs"] and summary.get("errors", 0) == 0)
    clear_rate = float(summary.get("source_clear_rate") or 0.0)
    time_s = float(summary.get("mean_time_per_true_source_s") or 1e9)
    return (-fullclear, -clear_rate, time_s)


def main():
    rounds = 6
    population = 14
    workers = 8
    rng = random.Random(20260913)
    base = load_json(CONFIGS / f"{BASE_NAME}.json")
    center = base["tune"]
    screen_groups, screen = balanced_seeds(3000, 2)
    expand_groups, expand = balanced_seeds(6000, 5)
    history = []

    for round_no in range(1, rounds + 1):
        names, scale = write_candidates(round_no, center, population, rng)
        screen_result, screen_summaries = evaluate(
            names, screen, workers, f"topoadapt_r{round_no:02d}_balanced14_screen")
        finalists = sorted(names, key=lambda name: rank_key(screen_summaries[name]))[:4]
        expand_result, expand_summaries = evaluate(
            finalists, expand, workers, f"topoadapt_r{round_no:02d}_balanced35_expand")
        winner = min(finalists, key=lambda name: rank_key(expand_summaries[name]))
        winner_summary = expand_summaries[winner]
        if winner_summary["fullclear_runs"] == winner_summary["runs"] and not winner_summary.get("errors"):
            center = load_json(CONFIGS / f"{winner}.json")["tune"]
        record = {
            "round": round_no,
            "scale": scale,
            "screen_run_dir": screen_result["run_dir"],
            "expand_run_dir": expand_result["run_dir"],
            "finalists": finalists,
            "winner": winner,
            "winner_expand_summary": winner_summary,
        }
        history.append(record)
        save_json(STATE, {
            "status": "running" if round_no < rounds else "complete",
            "method": "adaptive-route topology stochastic search with full-clear hard gate",
            "base": BASE_NAME,
            "screen_seed_groups": screen_groups,
            "expand_seed_groups": expand_groups,
            "screen_note": "Balanced N10-N16 screening set; not a formal independent test.",
            "expand_note": "Separate balanced N10-N16 expansion screen; not a formal independent test.",
            "parameters": PARAMS,
            "history": history,
        })
        print("ROUND_RESULT", json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
