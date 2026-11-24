#!/usr/bin/env python3
"""mock_hwinfo.py - fake HWiNFO REST API server for developing hwapiTop.

Serves /api/ping, /api/sensors/read and /api/sensors/sdb with a realistic
sensor tree (AMD CPU, NVIDIA GPU, memory, SSD, NIC, motherboard) so the TUI
can be built and tested without HWiNFO on Windows.

    ./mock_hwinfo.py --port 18080

Endpoints follow HWiNFO's REST API guide: `read` carries values only, `sdb`
carries the static description (unit, tooltip, hide/monitoring/logging flags).
A reading is "<name>": { "<type>": { "Value": ".." } }, the type being a
numeric string key (1 temp, 2 volt, 3 fan, 5 power, 6 clock, 7 usage, 8 other).
"""

import argparse
import json
import math
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

T0 = time.time()


def now() -> float:
    return time.time() - T0


# ---------------------------------------------------------------- sensor tree

def R(t, u, tool, fn, hide=0, mon=1, log=1):
    return {"kind": "r", "t": t, "u": u, "tool": tool, "fn": fn,
            "hide": hide, "mon": mon, "log": log}


def G(kids, t=8, u="", tool="", fn=None, hide=0, mon=1, log=1):
    return {"kind": "g", "kids": kids, "t": t, "u": u, "tool": tool, "fn": fn,
            "hide": hide, "mon": mon, "log": log}


def wave(base, amp, period, digits=1, phase=0.0):
    """A smoothly oscillating sensor value with a little noise."""
    def fn():
        v = base + amp * math.sin(now() / period + phase)
        return round(v + random.uniform(-abs(amp) * 0.03, abs(amp) * 0.03), digits)
    return fn


def cores(prefix, n, t, u, tool, fn):
    return {f"{prefix} {i}": R(t, u, tool.format(i), fn(i)) for i in range(n)}


def build_tree(cores_n):
    cpu = {
        "CPU Package": R(1, "°C", "CPU package temperature", wave(58, 14, 9)),
        "CPU (Tctl/Tdie)": R(1, "°C", "CPU die temperature", wave(60, 15, 11, phase=1)),
        "CPU Core Voltage (SVI2 TFN)": R(2, "V", "CPU core voltage", wave(1.15, 0.08, 13, 3)),
        "Total CPU Usage": R(7, "%", "Total CPU utilization", wave(38, 26, 7)),
        "CPU Package Power": R(5, "W", "CPU package power", wave(92, 34, 9, 2)),
        "CPU Fan": R(3, "RPM", "CPU fan speed", wave(1240, 180, 17, 0)),
        "Core Clocks": G({f"Core {i} Clock": R(6, "MHz", f"Core {i} clock",
                                              wave(4200 - i * 25, 300, 5 + i * 0.4, 1))
                          for i in range(cores_n)}),
        "Core Temperatures": G(cores("Core", cores_n, 1, "°C", "Core {} temperature",
                                     lambda i: wave(54 + i * 1.6, 9, 9 + i * 0.6))),
        "Core Usage": G(cores("Core", cores_n, 7, "%", "Core {} utilization",
                              lambda i: wave(35 + (i % 4) * 9, 30, 4 + i * 0.5, 0, phase=i))),
        "Core VIDs": G({"P-core 0 VID": R(2, "V", "Core 0 VID", wave(1.17, 0.05, 6, 3))},
                       t=2, u="V", fn=wave(1.172, 0.04, 6, 3)),
    }

    mem = {
        "Physical Memory Total": R(8, "MB", "Total physical memory", lambda: 65536),
        "Physical Memory Used": R(8, "MB", "Used physical memory", wave(24500, 9000, 23, 0)),
        "Physical Memory Load": R(7, "%", "Physical memory load", wave(37, 14, 23)),
        "Virtual Memory Total": R(8, "MB", "Total virtual memory", lambda: 32768),
        "Virtual Memory Used": R(8, "MB", "Used virtual memory", wave(11200, 3000, 31, 0)),
        "Virtual Memory Load": R(7, "%", "Virtual memory load", wave(34, 9, 31)),
        "Memory Clock": R(6, "MHz", "DRAM clock", lambda: 1800),
    }

    gpu = {
        "GPU Temperature": R(1, "°C", "GPU temperature", wave(62, 12, 13)),
        "GPU Hot Spot Temperature": R(1, "°C", "GPU hotspot", wave(74, 13, 13, phase=0.4)),
        "GPU Memory Junction Temperature": R(1, "°C", "GPU memory junction", wave(68, 10, 15)),
        "GPU Core Load": R(7, "%", "GPU core utilization", wave(46, 40, 5)),
        "GPU Memory Load": R(7, "%", "GPU memory utilization", wave(31, 22, 11)),
        "GPU Power": R(5, "W", "GPU board power", wave(180, 90, 7, 2)),
        "GPU Fan": R(3, "RPM", "GPU fan speed", wave(1500, 400, 19, 0)),
        "GPU Core Clock": R(6, "MHz", "GPU core clock", wave(1740, 120, 8, 1)),
        "GPU Memory Clock": R(6, "MHz", "GPU memory clock", lambda: 9501),
        "GPU Memory Used": R(8, "MB", "GPU memory used", wave(6100, 2200, 21, 0)),
        "GPU Memory Total": R(8, "MB", "GPU memory total", lambda: 10240),
        "GPU Fan PWM": R(7, "%", "GPU fan PWM duty", wave(52, 20, 19)),
    }

    drive = {
        "Drive Temperature": R(1, "°C", "Drive temperature", wave(41, 4, 41)),
        "Drive Remaining Life": R(7, "%", "SSD remaining life", wave(94, 0.5, 500)),
        "Total Host Writes": R(8, "GB", "Total host writes", wave(18400, 20, 900, 0)),
        "Drive Failure": R(0, "", "SMART failure prediction", lambda: "No"),
        "Free Fall Protection": R(0, "", "Free fall sensor", lambda: "No"),
    }

    net = {
        "Download Rate": R(8, "KB/s", "Current download rate", wave(2400, 2100, 6, 1)),
        "Upload Rate": R(8, "KB/s", "Current upload rate", wave(320, 300, 8, 1)),
        "Total Downloaded": R(8, "GB", "Total downloaded", wave(742, 3, 1200, 1)),
    }

    board = {
        "System Temperature": R(1, "°C", "Motherboard temperature", wave(33, 3, 47)),
        "CPU Temperature": R(1, "°C", "Socket temperature", wave(45, 7, 37)),
        "System Fan": R(3, "RPM", "Chassis fan", wave(820, 60, 29, 0)),
        "Vcore": R(2, "V", "Vcore rail", wave(1.19, 0.03, 12, 3)),
        "AVCC": R(2, "V", "3.3V rail", wave(3.31, 0.02, 25, 3)),
        "3VCC": R(2, "V", "3.3V rail", lambda: 3.312),
        "3VSB": R(2, "V", "Standby rail", lambda: 3.344),
        "12V": R(2, "V", "12V rail", wave(12.1, 0.08, 33, 2)),
        "Battery Voltage": R(2, "V", "CMOS battery", lambda: 3.056),
        # deliberately unmonitored: must NOT show up in /read
        "Chassis Intrusion": R(0, "", "Chassis intrusion", lambda: "Yes", mon=0),
    }

    system = {
        "Virtual Memory Committed": R(8, "MB", "Committed virtual memory", wave(19324, 4000, 27, 0)),
        "Commit Limit": R(8, "MB", "Commit limit", lambda: 81920),
    }

    return {
        "CPU [#0]: AMD Ryzen 9 5900X": G(cpu),
        "GPU [#0]: NVIDIA GeForce RTX 3080": G(gpu),
        "Memory": G(mem),
        "Drive: Samsung SSD 980 PRO 1TB": G(drive),
        "Network: Intel I225-V": G(net),
        "Motherboard": G(board),
        "System: ASUS PRIME X570-PRO": G(system),
    }


# ------------------------------------------------------------------ rendering

def fmt_value(node):
    v = node["fn"]()
    if isinstance(v, str):
        return v
    u = node["u"]
    if u in ("MB", "GB", "KB/s"):
        return f"{v:,.1f}" if u.endswith("/s") or u == "GB" else f"{v:,.0f}"
    if u == "MHz" or u == "RPM":
        return f"{v:,.0f}"
    if isinstance(v, float):
        return f"{v:.3f}" if u == "V" else f"{v:.1f}"
    return str(v)


def render_read(tree, prefix=()):
    """read tree: names -> type nodes with Value only; hidden/unmonitored omitted."""
    out = {}
    for name, node in tree.items():
        if node["hide"] or not node["mon"]:
            continue
        if node["kind"] == "r":
            out[name] = {str(node["t"]): {"Value": fmt_value(node)}}
        else:
            sub = render_read(node["kids"], prefix + (name,))
            if node["fn"] is not None:
                sub[str(node["t"])] = {"Value": fmt_value(node)}
            if sub:
                out[name] = sub
    return out


def type_meta(t):
    loc = {"eType": 0, "eTypeUnion": 0}
    return {"eType": t, "eTypeUnion": 0}, loc


def render_sdb(tree):
    """sdb tree: same shape, flags + Unit + Tooltip + t* metadata per node."""
    out = {}
    for name, node in tree.items():
        rloc, _ = type_meta(node["t"])
        flags = {"hide": node["hide"], "monitoring": node["mon"], "logging": node["log"]}
        if node["kind"] == "r":
            out[name] = {str(node["t"]): dict(
                flags, Unit=node["u"], Tooltip=node["tool"],
                tSensorLocation=rloc, tReadingLocation=rloc, tReadingType=dict(rloc))}
        else:
            sub = render_sdb(node["kids"])
            sub[str(node["t"])] = dict(flags, Unit=node["u"], Tooltip=node["tool"],
                                      tSensorLocation=rloc, tReadingLocation=rloc,
                                      tReadingType=dict(rloc))
            out[name] = sub
    return out


def stamp(t=None):
    """'11.11.2026 14:43:09.431' — server local time, HWiNFO's read timestamp format."""
    lt = time.localtime(t)
    ms = int((t if t else time.time()) % 1 * 1000) if t else int(time.time() % 1 * 1000)
    return time.strftime("%d.%m.%Y %H:%M:%S", lt) + f".{ms:03d}"


# -------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    cores = 8

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/ping":
            t3 = time.time()
            self._send(200, json.dumps({"pong": True, "t": round(t3 * 1000, 3)}))
        elif path == "/api/sensors/read":
            t_rs = time.time()
            body = render_read(build_tree(self.cores))
            t_re = time.time()
            doc = {"Version": 1,
                   "Timestamp RS": stamp(t_rs), "Timestamp": stamp(t_re),
                   "Timestamp RE": stamp(time.time()),
                   "Timestamp RS ms": round(t_rs * 1000, 3),
                   "Timestamp ms": round(t_re * 1000, 3),
                   "Timestamp RE ms": round(time.time() * 1000, 3)}
            doc.update(body)
            self._send(200, json.dumps(doc))
        elif path == "/api/sensors/sdb":
            doc = {"Version": 1}
            doc.update(render_sdb(build_tree(self.cores)))
            self._send(200, json.dumps(doc))
        else:
            self._send(404, f"Not Found: {path}", "text/plain")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        path = self.path.split("?")[0]
        if path in ("/api/sensors/filter/reset", "/api/sensors/update_display"):
            self._send(200, json.dumps({"ok": True}))
        elif path == "/api/sensors/filter/apply":
            try:
                doc = json.loads(body or b"{}")
            except ValueError:
                self._send(400, json.dumps({"error": "body is not JSON"}))
                return
            if not isinstance(doc.get("Version"), int):
                self._send(400, json.dumps({"error": "'Version' is missing"}))
                return
            self._send(200, json.dumps({"ok": True, "sensors": 3}))
        else:
            self._send(404, f"Not Found: {path}", "text/plain")


def main():
    ap = argparse.ArgumentParser(description="Mock HWiNFO REST API server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--cores", type=int, default=8)
    a = ap.parse_args()
    Handler.cores = a.cores
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"mock HWiNFO API on http://{a.host}:{a.port}  ({a.cores} cores)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
