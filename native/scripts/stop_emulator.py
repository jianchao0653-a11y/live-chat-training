"""Stop only this project's verified synthetic emulator and write a receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

from build_android import ROOT, SDK, OUT


SERIAL = "emulator-5556"
ADB = SDK / "platform-tools" / "adb.exe"


def adb(*args: str, timeout: int = 45) -> str:
    result = subprocess.run(
        [str(ADB), "-s", SERIAL, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError((result.stderr + result.stdout).strip())
    return result.stdout.strip()


def serial_is_present() -> bool:
    result = subprocess.run(
        [str(ADB), "devices"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    )
    return any(
        line.split()[:2] == [SERIAL, "device"] for line in result.stdout.splitlines()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", type=int, choices=[26, 34, 36], required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    if not serial_is_present():
        raise RuntimeError(f"{SERIAL} is not an online project emulator")
    if adb("shell", "getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("Target is not an emulator; no shutdown issued")

    names = adb("emu", "avd", "name").splitlines()
    if not names:
        raise RuntimeError("AVD identity was not returned; no shutdown issued")
    avd = names[0].strip()
    expected_avd = "LensPreview" if args.api == 36 else f"LensPreviewApi{args.api}"
    actual_api = adb("shell", "getprop", "ro.build.version.sdk")
    if avd != expected_avd or actual_api != str(args.api):
        raise RuntimeError(
            f"Expected {expected_avd}/API {args.api}, got {avd}/API {actual_api}; "
            "no shutdown issued"
        )
    if not re.fullmatch(r"LensPreview(?:Api(?:26|34))?", avd):
        raise RuntimeError("Target is outside the project AVD allowlist")

    evidence = {
        "status": "RUNNING",
        "at": datetime.now(timezone.utc).isoformat(),
        "serial": SERIAL,
        "avd": avd,
        "api": actual_api,
        "ownershipVerifiedBeforeShutdown": True,
        "kernelQemu": "1",
        "size": adb("shell", "wm", "size"),
        "density": adb("shell", "wm", "density"),
        "fontScale": adb("shell", "settings", "get", "system", "font_scale"),
        "reverseList": adb("reverse", "--list"),
        "mediaProjectionDump": adb("shell", "dumpsys", "media_projection"),
        "captureServiceDump": adb(
            "shell", "dumpsys", "activity", "services", "com.conversationlens.ime"
        ),
        "method": "adb emu kill after verified project AVD identity",
        "realPhone": False,
        "stalePidUsed": False,
        "existingBackendOrTunnelCommandsIssued": False,
    }

    evidence["shutdownResponse"] = adb("emu", "kill")
    absent = False
    consecutive_absent = 0
    for _ in range(40):
        time.sleep(0.5)
        if not serial_is_present():
            consecutive_absent += 1
            if consecutive_absent >= 4:
                absent = True
                break
        else:
            consecutive_absent = 0
    evidence["serialAbsentAfterShutdown"] = absent
    evidence["consecutiveAbsentChecks"] = consecutive_absent
    evidence["status"] = "PASS" if absent else "FAIL"
    evidence["completedAt"] = datetime.now(timezone.utc).isoformat()

    receipt = args.receipt
    if receipt is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        receipt = OUT / f"emulator-closure-api{args.api}-{stamp}.json"
    if not receipt.is_absolute():
        receipt = ROOT / receipt
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    process_record = OUT / "emulator-process.json"
    if process_record.exists():
        record = json.loads(process_record.read_text(encoding="utf-8-sig"))
        record.update(
            {
                "status": "stopped" if absent else "shutdown_failed",
                "stoppedAt": evidence["completedAt"],
                "stopMethod": evidence["method"],
            }
        )
        process_record.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(receipt)
    return 0 if absent else 1


if __name__ == "__main__":
    raise SystemExit(main())
