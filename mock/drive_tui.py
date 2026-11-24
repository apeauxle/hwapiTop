#!/usr/bin/env python3
"""Drive hwapiTop in a pty against the mock server and report the rendered screen.

Why a pty: the tool refuses to run its TUI when stdout is not a terminal and it
needs a real tty to read the window size. A pty also lets us send keystrokes and
render frames without putting a window on the human's desktop.

The screen model understands exactly the sequences hwapiTop emits:
  ESC[H            cursor home
  ESC[<row>;<col>H absolute cursor position
  ESC[2J           clear screen
  ESC[K            erase to end of line
  ESC[<n>m         SGR (ignored for text, tracked only to drop it)
Everything else is treated as text.
"""
import codecs, fcntl, os, pty, re, select, signal, struct, subprocess, sys, termios, time

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hwapitop")

CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


class Screen:
    """A tiny terminal model: enough of VT100 for hwapiTop's repaints."""

    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.clear()
        self.cx = self.cy = 0
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.pending = ""     # text held back when a chunk ends mid-escape

    def clear(self):
        self.grid = [[" "] * self.cols for _ in range(self.rows)]

    def feed_bytes(self, raw: bytes):
        self.feed(self.decoder.decode(raw))

    def feed(self, data: str):
        data = self.pending + data
        self.pending = ""
        i = 0
        n = len(data)
        while i < n:
            ch = data[i]
            if ch == "\x1b":
                m = CSI.match(data, i)
                if m:
                    self._csi(m.group(1), m.group(2))
                    i = m.end()
                    continue
                # A chunk can end anywhere inside a CSI, e.g. "\x1b[38;5;23"
                # followed by "9m". Hold the whole tail back and replay it
                # with the next chunk instead of printing escape params.
                if re.match(r"\x1b\[[0-9;?]*$", data[i:]):
                    self.pending = data[i:]
                    return
                if i + 2 > n:
                    self.pending = data[i:]
                    return
                i += 2          # unknown two-byte escape
                continue
            if ch == "\n":
                self.cy = min(self.cy + 1, self.rows - 1)
                self.cx = 0
            elif ch == "\r":
                self.cx = 0
            elif ch == "\b":
                self.cx = max(0, self.cx - 1)
            else:
                if self.cy < self.rows and self.cx < self.cols:
                    self.grid[self.cy][self.cx] = ch
                self.cx += 1
            i += 1

    def _csi(self, params: str, final: str):
        if final == "H" or final == "f":
            parts = [p for p in params.split(";") if p]
            row = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 1
            col = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 1
            self.cy = max(0, min(row - 1, self.rows - 1))
            self.cx = max(0, min(col - 1, self.cols - 1))
        elif final == "J":
            if params in ("2", "3"):
                self.clear()
                self.cx = self.cy = 0
        elif final == "K":
            if 0 <= self.cy < self.rows:
                for c in range(self.cx, self.cols):
                    self.grid[self.cy][c] = " "
        # SGR and everything else: no visual effect on plain text

    def lines(self):
        return ["".join(r).rstrip() for r in self.grid]


class Session:
    def __init__(self, args, cols=140, rows=38):
        self.cols, self.rows = cols, rows
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.proc = subprocess.Popen(
            args, stdin=slave, stdout=slave, stderr=slave,
            env={**os.environ, "TERM": "xterm-256color"},
            start_new_session=True, close_fds=True)
        os.close(slave)
        self.screen = Screen(cols, rows)

    def pump(self, seconds):
        """Read output for `seconds`, feeding the screen model."""
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([self.master], [], [], 0.05)
            if not r:
                continue
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            self.screen.feed_bytes(chunk)

    def send(self, keys: str):
        os.write(self.master, keys.encode())

    def close(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        try:
            os.close(self.master)
        except OSError:
            pass


def dump(screen, header=""):
    lines = screen.lines()
    if header:
        print(header)
    for i, l in enumerate(lines, 1):
        print(f"{i:2d}|{l}|")
    bad = [(i, len(l)) for i, l in enumerate(lines, 1)
           if len(l) not in (0, screen.cols)]
    # trailing spaces are stripped by .rstrip(), so only over-long lines matter
    over = [(i, n) for i, n in bad if n > screen.cols]
    print(f"\nrows={screen.rows} cols={screen.cols} overlong={over or 'none'}")
    return not over


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:18080"
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 140
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 38
    s = Session([APP, "--url", url, "--interval", "1"], cols, rows)
    ok = True
    try:
        s.pump(4.0)                     # connect + first frames
        s.pump(6.0)                     # let history build
        ok &= dump(s.screen, "=== live frame after ~10s ===")

        # pause must freeze the clock/updates counter
        s.send("p"); s.pump(2.5)
        before = [l for l in s.screen.lines() if "updates" in l]
        s.pump(2.5)
        after = [l for l in s.screen.lines() if "updates" in l]
        paused_ok = bool(before) and before == after and "PAUSED" in "".join(s.screen.lines())
        print(f"pause: {'OK' if paused_ok else 'FAIL'} ({before} -> {after})")
        ok &= paused_ok
        s.send("p"); s.pump(2.0)

        # interval keys must change the header
        s.send("+"); s.pump(1.5)
        plus_ok = any("poll 2s" in l for l in s.screen.lines())
        print(f"interval +: {'OK' if plus_ok else 'FAIL'}")
        ok &= plus_ok
        s.send("-"); s.pump(1.5)

        s.send("q"); s.pump(2.0)
        quit_ok = s.proc.poll() is not None
        print(f"quit: {'OK' if quit_ok else 'FAIL'} (rc={s.proc.poll()})")
        ok &= quit_ok
    finally:
        s.close()
    print("\nRESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
