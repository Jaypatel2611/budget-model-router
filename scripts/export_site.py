"""Copy the latest run results into public/ for the static site. Re-run after `python -m src.run`."""
import pathlib, shutil, sys

root = pathlib.Path(__file__).resolve().parent.parent
for name in ("report.json", "output.jsonl"):
    src = root / "results" / name
    if not src.exists():
        sys.exit(f"missing {src}; run `python -m src.run` first")
    shutil.copy(src, root / "public" / name)
    print("copied", name)
