from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
CHUNK_DIR = ROOT / "bundle_b64"
ZIP_PATH = ROOT / "iter076_source_bundle.zip"
WORKSPACE = ROOT / "workspace"
BENCHMARK = WORKSPACE / "code" / "benchmark_iter076.py"
EXPECTED_SHA256 = "73a3027f7f26f762cc5259968539237c57227e088f345e46a0b860d6de034757"


def rebuild_bundle() -> bytes:
    parts = sorted(CHUNK_DIR.glob("part_*.txt"))
    if not parts:
        raise FileNotFoundError(f"no bundle chunks found in {CHUNK_DIR}")
    payload = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    data = base64.b64decode(payload, validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"bundle SHA256 mismatch: {digest} != {EXPECTED_SHA256}")
    ZIP_PATH.write_bytes(data)
    return data


def main() -> int:
    data = rebuild_bundle()
    print(f"[iter076] bundle verified: {EXPECTED_SHA256} ({len(data)} bytes)")
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        zf.extractall(ROOT)
    if not BENCHMARK.exists():
        raise FileNotFoundError(f"benchmark not found after extraction: {BENCHMARK}")
    print("[iter076] running frozen 35-case validation...")
    return subprocess.run([sys.executable, str(BENCHMARK)], cwd=str(WORKSPACE), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
