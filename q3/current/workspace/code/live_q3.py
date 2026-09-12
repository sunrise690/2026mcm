from __future__ import annotations

import argparse
import time
from pathlib import Path

from live_runner import SimulatorClient, SimulatorError
from q3_controller import run_q3_particle


def main() -> None:
    ap = argparse.ArgumentParser(description="CUMCM 2026 B题 Q3 在线控制器 commit10-current")
    ap.add_argument("--robot-id", required=True, help="模拟器显示的当前队号")
    ap.add_argument("--base-url", default="http://127.0.0.1:2026")
    ap.add_argument("--log", default=None, help="可选 JSONL 日志路径")
    args = ap.parse_args()

    code_dir = Path(__file__).resolve().parent
    workspace = code_dir.parent
    figures = workspace / "figures"
    try:
        figures.mkdir(parents=True, exist_ok=True)
        default_log_dir = figures
    except PermissionError:
        default_log_dir = code_dir / "logs"
        default_log_dir.mkdir(parents=True, exist_ok=True)
    if args.log:
        log_path = Path(args.log).expanduser().resolve()
    else:
        log_path = default_log_dir / f"live_q3_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"

    client = SimulatorClient(args.robot_id, args.base_url, log_path=log_path)
    try:
        cleared = run_q3_particle(client)
        vt = client.current_virtual_time_s
        avg = vt / cleared if cleared else float("nan")
        print("-" * 62, flush=True)
        if cleared:
            print(f"统计：总虚拟时间 {vt:.3f} s，程序记录清除 {cleared} 个，平均 {avg:.3f} s/源", flush=True)
        else:
            print(f"统计：总虚拟时间 {vt:.3f} s，程序未记录到清除成功", flush=True)
        print(f"日志：{log_path}", flush=True)
    except SimulatorError as exc:
        print(f"运行失败：{exc}", flush=True)
        raise


if __name__ == "__main__":
    main()
