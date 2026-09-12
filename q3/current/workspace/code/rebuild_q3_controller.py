from pathlib import Path

here = Path(__file__).resolve().parent
parts = [here / f"q3_controller.py.part{i}" for i in range(1, 5)]
out = here / "q3_controller.py"
out.write_text("".join(p.read_text(encoding="utf-8") for p in parts), encoding="utf-8")
print(f"rebuilt: {out}")
