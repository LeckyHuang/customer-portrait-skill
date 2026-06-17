"""
Customer Portrait Service - Windows installer
Usage: python install.py
"""
import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SERVICE_NAME = "CustomerPortraitService"
PORT = 8099


def run(cmd, **kwargs):
    print(f"  > {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def check(cmd):
    return subprocess.run(cmd, capture_output=True).returncode == 0


def find_nssm():
    candidates = [
        Path("C:/tools/nssm.exe"),
        Path("C:/nssm/nssm.exe"),
        ROOT / "tools" / "nssm.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def download_nssm():
    tools = ROOT / "tools"
    tools.mkdir(exist_ok=True)
    zip_path = tools / "nssm.zip"
    print("  Downloading NSSM...")
    urllib.request.urlretrieve("https://nssm.cc/release/nssm-2.24.zip", zip_path)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tools / "nssm_tmp")
    src = tools / "nssm_tmp" / "nssm-2.24" / "win64" / "nssm.exe"
    dst = tools / "nssm.exe"
    shutil.copy2(src, dst)
    return dst


def main():
    print("\n=== Customer Portrait Service - Install ===\n")

    # Check config.yaml
    if not (ROOT / "config.yaml").exists():
        print("[ERROR] config.yaml not found in", ROOT)
        input("Press Enter to exit...")
        sys.exit(1)

    # Step 1: Install dependencies
    print("[1/3] Installing dependencies...")
    venv = ROOT / ".venv"
    if venv.exists():
        print("  Removing old .venv...")
        shutil.rmtree(venv)
    run([sys.executable, "-m", "venv", str(venv)])
    pip = venv / "Scripts" / "pip.exe"
    if not pip.exists():
        print("[ERROR] venv creation failed")
        input("Press Enter to exit...")
        sys.exit(1)
    run([pip, "install", "--upgrade", "pip", "-q"])
    result = run([pip, "install", "-r", str(ROOT / "requirements.txt")])
    if result.returncode != 0:
        print("[ERROR] pip install failed")
        input("Press Enter to exit...")
        sys.exit(1)
    print("  Done.\n")

    # Step 2: Register Windows service
    print("[2/3] Setting up Windows service...")
    nssm = find_nssm()
    if not nssm:
        try:
            nssm = download_nssm()
        except Exception as e:
            print(f"[ERROR] Failed to get NSSM: {e}")
            print("  Download nssm.exe from https://nssm.cc and put it in", ROOT / "tools")
            input("Press Enter to exit...")
            sys.exit(1)

    # Remove old service
    if check(["sc", "query", SERVICE_NAME]):
        print("  Removing old service...")
        run([nssm, "stop", SERVICE_NAME])
        run([nssm, "remove", SERVICE_NAME, "confirm"])

    (ROOT / "logs").mkdir(exist_ok=True)
    python_exe = venv / "Scripts" / "python.exe"

    run([nssm, "install", SERVICE_NAME, str(python_exe), "server.py"])
    run([nssm, "set", SERVICE_NAME, "AppDirectory", str(ROOT)])
    run([nssm, "set", SERVICE_NAME, "DisplayName", "Customer Portrait Service"])
    run([nssm, "set", SERVICE_NAME, "Start", "SERVICE_AUTO_START"])
    run([nssm, "set", SERVICE_NAME, "AppStdout", str(ROOT / "logs" / "service.log")])
    run([nssm, "set", SERVICE_NAME, "AppStderr", str(ROOT / "logs" / "error.log")])
    run([nssm, "set", SERVICE_NAME, "AppRotateFiles", "1"])
    run([nssm, "set", SERVICE_NAME, "AppRotateBytes", "5242880"])
    print("  Service registered.\n")

    # Step 3: Start and verify
    print("[3/3] Starting service...")
    run([nssm, "start", SERVICE_NAME])

    import time
    time.sleep(5)

    try:
        import urllib.request as req
        req.urlopen(f"http://localhost:{PORT}/health", timeout=5)
        print(f"\n=== Install complete ===")
        print(f"Health: http://localhost:{PORT}/health")
        print(f"Service: {SERVICE_NAME} (auto-start on boot)")
    except Exception:
        print(f"\n[WARN] Service registered but not responding yet.")
        print(f"  Check: http://localhost:{PORT}/health")
        print(f"  Logs:  {ROOT / 'logs' / 'service.log'}")

    print()
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
