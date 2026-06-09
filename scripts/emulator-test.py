#!/usr/bin/env python3
"""Navigate Santander clone on emulator and record UI + logcat."""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "com.azemon.santanderclone"
APK = ROOT / "SantanderClone-signed.apk"
SERIAL = __import__("os").environ.get("ANDROID_SERIAL", "emulator-5554")
OUT = ROOT / "screenshots" / f"emulator-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)


def adb(*args: str, check: bool = True) -> str:
    cmd = ["adb", "-s", SERIAL, *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"adb failed: {' '.join(cmd)}\n{r.stderr}")
    return (r.stdout or "") + (r.stderr or "")


def tap_xy(x: int, y: int) -> None:
    print(f"  tap {x},{y}")
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(2)


def tap_center(bounds: str) -> None:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not m:
        return
    x1, y1, x2, y2 = map(int, m.groups())
    tap_xy((x1 + x2) // 2, (y1 + y2) // 2)


def type_text(text: str) -> None:
    safe = text.replace(" ", "%s")
    adb("shell", "input", "text", safe)


def dump_ui(name: str) -> list[dict]:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml", check=False)
    local = OUT / f"{name}.xml"
    adb("pull", "/sdcard/ui.xml", str(local), check=False)
    items = []
    try:
        root = ET.parse(local).getroot()
        for n in root.iter("node"):
            t = (n.attrib.get("text") or "").strip()
            d = (n.attrib.get("content-desc") or "").strip()
            if not t and not d:
                continue
            items.append(
                {
                    "text": t,
                    "desc": d,
                    "id": n.attrib.get("resource-id", ""),
                    "clickable": n.attrib.get("clickable") == "true",
                    "bounds": n.attrib.get("bounds", ""),
                }
            )
    except Exception as e:
        print(f"  warn parse ui: {e}")
    return items


def shot(name: str) -> None:
    path = OUT / f"{name}.png"
    with open(path, "wb") as f:
        subprocess.run(
            ["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
            stdout=f,
            check=False,
        )
    print(f"  screenshot {path.name} ({path.stat().st_size} bytes)")


def find(items: list[dict], *needles: str) -> dict | None:
    for item in items:
        blob = f"{item['text']} {item['desc']} {item['id']}".lower()
        if all(n.lower() in blob for n in needles):
            return item
    return None


def record_step(name: str, note: str = "") -> list[dict]:
    print(f"\n=== {name} ===")
    items = dump_ui(name)
    shot(name)
    summary = OUT / "walkthrough.txt"
    with summary.open("a") as f:
        f.write(f"\n## {name}\n")
        if note:
            f.write(f"{note}\n")
        for it in items[:40]:
            f.write(f"- {it['text'] or it['desc']} [{it['bounds']}] id={it['id']}\n")
    return items


def main() -> None:
    print(f"Output: {OUT}")
    subprocess.run(["curl", "-sf", "https://project-efnt2.vercel.app/health"], check=False)
    subprocess.run(
        ["curl", "-sf", "https://project-efnt2.vercel.app/santander/eeic/global_position_app?active_only=true"],
        check=False,
    )

    adb("install", "-r", "--no-incremental", str(APK), check=False)
    adb("shell", "pm", "clear", PKG, check=False)
    adb("shell", "am", "force-stop", "com.google.android.apps.wellbeing", check=False)
    adb("logcat", "-c", check=False)

    adb(
        "shell",
        "am",
        "start",
        "-n",
        f"{PKG}/es.bancosantander.apps.mobile.android.activities.PublicActivity",
    )
    time.sleep(20)

    items = record_step("01-login", "Public/login screen")
    user = find(items, "username") or find(items, "enter with your username")
    pwd = find(items, "password") or find(items, "enter your password")
    login = find(items, "login")

    if user:
        tap_center(user["bounds"])
        type_text("demo")
    if pwd:
        tap_center(pwd["bounds"])
        type_text("demo123")
    time.sleep(1)
    items = record_step("02-credentials", "Filled demo/demo123")

    if login:
        tap_center(login["bounds"])
    else:
        tap_xy(540, 1330)
    time.sleep(25)
    items = record_step("03-post-login", "After login submit")

    # Bottom navigation — scan for tab labels
    tabs = []
    for it in items:
        blob = f"{it['text']} {it['desc']}".lower()
        if it["clickable"] and any(
            k in blob
            for k in (
                "home",
                "accounts",
                "cards",
                "payments",
                "for you",
                "para si",
                "contas",
                "cartões",
                "pagamentos",
                "início",
                "personal",
            )
        ):
            tabs.append(it)

    if not tabs:
        # fallback: 5 evenly spaced taps along bottom bar
        for i, x in enumerate([108, 324, 540, 756, 972], start=1):
            tap_xy(x, 2280)
            record_step(f"04-tab-{i}", f"Bottom nav tap x={x}")
    else:
        for i, tab in enumerate(tabs[:6], start=1):
            tap_center(tab["bounds"])
            record_step(f"04-tab-{i}", tab["text"] or tab["desc"])

    # Menu / settings
    menu = find(items, "menu") or find(items, "icn_menu")
    if menu:
        tap_center(menu["bounds"])
        record_step("05-menu", "Opened side menu")

    log = subprocess.run(
        ["adb", "-s", SERIAL, "logcat", "-d"],
        capture_output=True,
        text=True,
    )
    err_path = OUT / "errors.txt"
    fatals = []
    lines = log.stdout.splitlines()
    for i, line in enumerate(lines):
        if "FATAL EXCEPTION" in line:
            fatals.extend(lines[i : i + 25])
    err_path.write_text(
        "=== FATAL ===\n"
        + "\n".join(fatals[:200])
        + "\n\n=== GP/NET ===\n"
        + "\n".join(
            l
            for l in lines
            if re.search(
                r"global.position|Load global|JsonParse|PortugalError|ServiceException|NetworkException|santanderclone.*E ",
                l,
                re.I,
            )
        )[-80:]
    )
    print(f"\nDone → {OUT}")
    print(f"Errors → {err_path}")


if __name__ == "__main__":
    main()
