"""Lightweight local web server and execution bridge for the Day Trader Skill Hub."""

import http.server
import json
import os
import re
import socket
import shutil
import subprocess
import tempfile
import sys
import urllib.parse
import webbrowser
from http import HTTPStatus

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8000
# The hub keeps its own saved state (trader/*.json) here, away from the repo root.
STATE = os.path.join(ROOT, ".hub")


def run_cmd(cmd, cwd=None):
    cwd = cwd or ROOT
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)


class TradingHubHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # Enable CORS for local cross-origin file:// or localhost access
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/api/status":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"status": "online", "python": sys.executable, "market_default": "IN"}
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/run":
            step = params.get("step", ["all"])[0]
            market = params.get("market", ["IN"])[0].upper()
            symbol = params.get("symbol", ["RELIANCE.NS" if market == "IN" else "TSLA"])[0]
            entry_price = params.get("entry", ["2500" if market == "IN" else "364.18"])[0]
            stop_price = params.get("stop", ["2475" if market == "IN" else "358.32"])[0]
            target_price = params.get("target", ["2550" if market == "IN" else "370.04"])[0]

            # Values are interpolated into shell commands: reject anything unsafe.
            safe = re.compile(r"^[A-Za-z0-9._:^&=-]{1,32}$")
            if not all(safe.match(v) for v in (market, symbol, entry_price, stop_price, target_price)):
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"output": "Invalid parameter", "code": 1}).encode("utf-8"))
                return

            res = self.execute_step(step, market, symbol, entry_price, stop_price, target_price)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Default to index.html for root path
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def execute_step(self, step, market, symbol, entry_price, stop_price, target_price):
        py = sys.executable
        trader_dir = os.path.join(STATE, "trader")
        os.makedirs(trader_dir, exist_ok=True)

        # Initialize config if missing
        cfg_file = os.path.join(trader_dir, "config.json")
        marker = os.path.join(trader_dir, ".config_market")
        last = open(marker).read().strip() if os.path.exists(marker) else None
        if not os.path.exists(cfg_file) or last != market:
            src = "config.example.india.json" if market == "IN" else "config.example.json"
            cfg_src = os.path.join(ROOT, "trader-budget", src)
            if os.path.exists(cfg_src):
                with open(cfg_src, "r", encoding="utf-8") as f_in:
                    cdata = json.load(f_in)
                with open(cfg_file, "w", encoding="utf-8") as f_out:
                    json.dump(cdata, f_out, indent=2)
                with open(marker, "w") as f_m:
                    f_m.write(market)

        m_flag = "--market %s" % market

        cmd_map = {
            "clock": "%s trader-alerts/alerts.py clock %s" % (py, m_flag),
            # Scan the first 500 symbols (about a minute). If the market is closed, replay 10:15.
            "scanner": "%s trader-scanner/scan.py universe %s && (%s trader-scanner/scan.py orb %s --limit 500 || %s trader-scanner/scan.py orb %s --limit 500 --at 10:15)" % (
                py, m_flag, py, m_flag, py, m_flag),
            "news": "%s trader-news/news.py --tickers %s %s" % (py, symbol, m_flag),
            "entry": "%s trader-entry/entry.py check %s %s --write" % (py, symbol, m_flag),
            "exit": "%s trader-exit/exit.py plan %s --symbol %s --entry %s --stop price:%s --target price:%s --time 10:15 --write" % (
                py, m_flag, symbol, entry_price, stop_price, target_price),
            "timemachine": "%s trader-timemachine/timemachine.py run %s --replays 500 --write" % (py, m_flag),
            "budget": "%s trader-budget/size.py %s --write" % (py, m_flag),
            "risk": "%s trader-risk/check.py %s" % (py, m_flag),
            "broker": "%s trader-broker/ticket.py show %s" % (py, m_flag),
            "alerts": "%s trader-alerts/alerts.py clock %s" % (py, m_flag),
            "insider": "%s trader-pelosi/insider.py pit --promoter-only" % py,
            "deals": "%s trader-pelosi/insider.py deals" % py,
            "tests": "%s -m unittest discover -s tests" % py,
        }

        if step == "all":
            # Execute full pipeline sequentially
            all_steps = ["clock", "exit", "budget", "risk", "broker"]
            outputs = []
            overall_code = 0
            for s in all_steps:
                c = cmd_map[s]
                p = run_cmd(c.replace(" trader-", " ../trader-"), cwd=STATE)
                out = (p.stdout or "") + (("\n[STDERR]: " + p.stderr) if p.stderr else "")
                outputs.append("=== [%s] ===\n$ %s\n\n%s" % (s.upper(), c, out.strip()))
                if p.returncode != 0:
                    overall_code = p.returncode

            return {
                "step": "all",
                "market": market,
                "command": "pipeline: " + " -> ".join(all_steps),
                "output": "\n\n".join(outputs),
                "code": overall_code
            }

        cmd = cmd_map.get(step, cmd_map["clock"])
        if step == "tests":
            # Run in a clean copy so saved trading state in trader/ cannot affect the tests.
            with tempfile.TemporaryDirectory() as tmp:
                work = os.path.join(tmp, "repo")
                shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", ".hub", "trader", "__pycache__"))
                p = run_cmd(cmd, cwd=work)
        else:
            p = run_cmd(cmd.replace(" trader-", " ../trader-"), cwd=STATE)
        out = (p.stdout or "") + (("\n[STDERR]: " + p.stderr) if p.stderr else "")

        return {
            "step": step,
            "market": market,
            "command": cmd,
            "output": out.strip(),
            "code": p.returncode
        }


def main():
    url = "http://localhost:%d" % PORT
    print("=" * 70)
    print("  Day Trader Skill Hub - Local Server Bridge")
    print("=" * 70)

    # If the hub is already running, just open it.
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            print("Already running at %s - opening browser." % url)
            webbrowser.open(url)
            return

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), TradingHubHandler)
    print("Running at %s  (Ctrl+C or close this window to stop)" % url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
