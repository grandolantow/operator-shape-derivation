"""Compatibility entry for pre-suite installations."""
from pathlib import Path
import runpy

_SOURCE = Path(__file__).resolve().parents[1] / "skills/operator-shape-derivation/scripts/check_execution_contract.py"
if __name__ == "__main__":
    runpy.run_path(str(_SOURCE), run_name="__main__")
else:
    globals().update({key: value for key, value in runpy.run_path(str(_SOURCE)).items() if not key.startswith("__")})
