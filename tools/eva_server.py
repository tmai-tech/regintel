#!/usr/bin/env python3
"""
Optional local Eva API for LLM chat (keeps XAI_API_KEY server-side).

  export XAI_API_KEY=...
  .venv/bin/python tools/eva_server.py --port 8787

Endpoints:
  GET  /health
  GET  /api/eva/meta
  POST /api/eva/ask  {"question":"...","k":8}
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from eva_agent import ask, load_summaries  # type: ignore
from eva_llm import get_client  # type: ignore


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/health", "/api/eva/health"):
            return self._json(
                200,
                {
                    "ok": True,
                    "agent": "Eva",
                    "summaries": len(load_summaries()),
                    "llm": get_client() is not None,
                },
            )
        if path == "/api/eva/meta":
            return self._json(
                200,
                {
                    "agent": "Eva",
                    "summaries": len(load_summaries()),
                    "llm": get_client() is not None,
                },
            )
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/eva/ask":
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        q = (payload.get("question") or "").strip()
        if not q:
            return self._json(400, {"error": "question required"})
        k = int(payload.get("k") or 8)
        try:
            res = ask(q, k=k)
            return self._json(200, res)
        except Exception as e:
            return self._json(500, {"error": str(e)[:400]})

    def log_message(self, fmt, *args):
        sys.stderr.write("EvaAPI " + (fmt % args) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    args = p.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"Eva API on http://{args.host}:{args.port}  "
        f"summaries={len(load_summaries())} llm={get_client() is not None}"
    )
    httpd.serve_forever()


if __name__ == "__main__":
    main()
