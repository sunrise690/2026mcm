from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "iter076_source_bundle.zip"
WORKSPACE = ROOT / "workspace"
BENCHMARK = WORKSPACE / "code" / "benchmark_iter076.py"


def main() -> int:
    if not BUNDLE.exists():
        raise FileNotFoundError(f"missing source bundle: {BUNDLE}")

    if not BENCHMARK.exists():
        with zipfile.ZipFile(BUNDLE, "r") as zf:
            zf.extractall(ROOT)

    if not BENCHMARK.exists():
        raise FileNotFoundError(f"benchmark not found after extraction: {BENCHMARK}")

    print(f"[iter076] workspace: {WORKSPACE}")
    print("[iter076] running frozen 35-case validation...")
    result = subprocess.run(
        [sys.executable, str(BENCHMARK)],
        cwd=str(WORKSPACE),
        check=False,
    )
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
