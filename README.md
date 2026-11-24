# hwapiTop

Terminal monitor (btop-style) for a machine running [HWiNFO](https://www.hwinfo.com/)
with its Remote Center REST API. Polls the server, matches every reading against
the sensor database from `/api/sensors/sdb`, and renders CPU / GPU / memory /
network panels in the terminal.

Requires: `bash` (5+), `curl`, `jq`.

## Usage

```
./hwapitop --url <host> [options]
```

| Option | Description |
| --- | --- |
| `--url <host>` | server address: `192.168.1.50`, `192.168.1.50:8080`, `http://host:port`, `https://host:port` (no scheme: tries https, then http; missing port means 8080) |
| `-i, --interval <s>` | poll interval in seconds; fractional values (0.1 .. 0.9) poll in 100 ms steps (default 2) |
| `-t, --timeout <s>` | per-request timeout (default 5) |
| `--verify` | verify the TLS certificate (default: accept self-signed) |
| `--once` | print one snapshot and exit (no TUI, works without a tty) |
| `--list` | print the sensor table (name, type, value, unit) and exit |
| `--render WxH` | print one rendered frame (for testing) |
| `--no-color` | disable colors |

TUI keys: `q` quit · `p` pause · `+`/`-` poll interval (1 s steps, 100 ms below 1 s) · `r` reload sensor db · `h` help

## Examples

```
./hwapitop --url 192.168.1.100:8037
./hwapitop --url http://192.168.1.100:8037 --interval 0.5
./hwapitop --url 192.168.1.100:8037 --once
```

## Server side

Run HWiNFO on the target Windows machine and start its Remote Center REST
API. Give the actual port in `--url` (a missing port means 8080). Sensor names
follow the HWiNFO install language — both English and Russian names are
matched.

## Mock server

For development without the real machine:

```
bash mock/start_mock.sh [port]     # default 18080, log in mock/mock.log
./hwapitop --url http://127.0.0.1:18080
```
