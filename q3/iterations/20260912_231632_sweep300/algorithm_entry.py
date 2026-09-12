"""Q3 离线迭代入口：公开反馈控制器的可复现配置。

核心控制器在本地 q3_iterations/src/tunable_controller.py；该入口固定
离线评测使用的参数，便于云端复现同一候选。
"""
from pathlib import Path
import json

ITERATION = "20260912_231632_sweep300"
CONFIG = {
    "controller": "tunable",
    "tune": {
        "geometry_mode": 0,
        "particle_n": 32000,
        "particle_rebuild_n": 64000,
        "service_iters": 2,
        "finish_choose_cheapest": 0,
        "bootstrap_info_w": 220,
        "bootstrap_gain_w": 0.08,
        "bootstrap_move_w": 0.08,
        "route_scan_thr_low": 0.12,
        "route_scan_thr_mid": 0.10,
        "route_scan_thr_high": 0.074,
        "stop_thr_10": 0.79,
        "stop_thr_11": 0.83,
        "stop_thr_12": 0.86,
        "stop_thr_13": 0.875,
        "stop_thr_14": 0.88,
        "stop_thr_15": 0.88,
    },
}


def write_config(path="q3_config.json"):
    Path(path).write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_config()
    print(f"prepared {ITERATION}")
