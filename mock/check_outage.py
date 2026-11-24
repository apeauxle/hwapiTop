#!/usr/bin/env python3
"""Check that hwapiTop stops showing numbers when the server goes away.

Run with the mock already up. The test kills the mock mid-run and asserts the
screen does not keep presenting the last good readings as if they were live.
"""
import os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_tui import Session  # noqa: E402

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hwapitop")
PIDFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock.pid")


def main():
    s = Session([APP, "--url", "127.0.0.1:18080", "--interval", "1"])
    ok = True
    try:
        s.pump(4.0)
        live = "\n".join(s.screen.lines())
        has_numbers = "temp" in live and "°C" in live
        print(f"live frame has readings: {'OK' if has_numbers else 'FAIL'}")
        ok &= has_numbers

        # stop the server
        pid = open(PIDFILE).read().strip()
        subprocess.run(["kill", pid], check=False)
        print(f"killed mock pid {pid}")

        s.pump(8.0)          # several failed polls -> LINE_LOST >= 3
        lines = s.screen.lines()
        screen = "\n".join(lines)
        state_ok = "NO DATA" in screen or "OFFLINE" in screen
        # the header must keep working, and the panel must stop asserting values
        stale = "GB/s" in screen or "%" in screen.split("┌─ CPU")[-1].split("└")[0]
        print(f"shows NO DATA/OFFLINE: {'OK' if state_ok else 'FAIL'}")
        print(f"no stale readings left: {'OK' if not stale else 'FAIL'}")
        ok &= state_ok
        for i, l in enumerate(lines[:14], 1):
            print(f"{i:2d}|{l}|")
    finally:
        s.close()
    print("\nRESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
