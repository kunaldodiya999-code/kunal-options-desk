"""Setup on the PC. Easiest: double-click setup_desk.bat in the kunal-options-desk folder.
(Same thing by hand, from inside that folder:  python setup_pc.py)

1. makes the desk's own Python box (.venv), or repairs it if it is broken;
2. installs everything into it (requirements.txt, including the parts FYERS' library needs);
3. installs fyers-apiv3 WITHOUT its strict old pins (its aiohttp 3.9.3 cannot install on new Python on Windows);
4. checks FYERS' library loads and runs the tests.
Safe to run again at any time (after every update). No PowerShell script permission is needed.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FYERS = "fyers-apiv3==3.2.0"
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


class Stop(Exception):
    pass


def run(step: str, *args, fatal: bool = True) -> bool:
    print(f"\n=== {step}", flush=True)
    print(">>", " ".join(str(a) for a in args), flush=True)
    ok = subprocess.run([str(a) for a in args], cwd=ROOT).returncode == 0
    if not ok and fatal:
        raise Stop(step)
    return ok


def venv_works() -> bool:
    if not PY.exists():
        return False
    try:
        return subprocess.run([str(PY), "-c", "import sys, pip"], cwd=ROOT, capture_output=True).returncode == 0
    except OSError:
        return False


def main() -> int:
    print(f"Kunal Options Desk setup in: {ROOT}")
    print(f"Python used to make the box: {sys.executable} ({sys.version.split()[0]})")
    if sys.version_info < (3, 10):
        print("\nThis Python is too old (3.10 or newer is needed). Install Python from python.org and try again.")
        return 1
    try:
        if not venv_works():
            if VENV.exists():
                print("\nThe .venv box is broken or from another computer: making a new one.")
                shutil.rmtree(VENV, ignore_errors=True)
            run("Step 1 of 5: making the Python box (.venv)", sys.executable, "-m", "venv", VENV)
        else:
            print("\n=== Step 1 of 5: the Python box (.venv) is already there")
        run("Step 2 of 5: updating pip", PY, "-m", "pip", "install", "--upgrade", "pip", fatal=False)
        run("Step 3 of 5: installing the desk's packages", PY, "-m", "pip", "install", "-r", "requirements.txt")
        run("Step 4 of 5: installing FYERS' library", PY, "-m", "pip", "install", "--no-deps", FYERS)
        run("Step 4 of 5: checking FYERS' library loads", PY, "-W", "ignore", "-c",
            "from fyers_apiv3 import fyersModel; from fyers_apiv3.FyersWebsocket import data_ws; "
            "print('fyers-apiv3 OK')")
        run("Step 5 of 5: running the tests (should end with 'passed')", PY, "-m", "pytest", "tests", "-q",
            "-p", "no:cacheprovider", "-W", "ignore")
    except Stop as stop:
        print("\n" + "!" * 70)
        print(f"SETUP STOPPED at: {stop}")
        print("Nothing is broken on your PC. Please send Claude a screenshot of this whole window.")
        print("!" * 70)
        return 1
    print("\n" + "=" * 70)
    print("ALL DONE. Setup worked.")
    print("  * Pretend prices (to look around):  double-click demo_desk.bat")
    print("  * Real FYERS prices:                double-click start_desk.bat")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
