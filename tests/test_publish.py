# -*- coding: utf-8 -*-
"""Test bước đăng lên GitHub với một GitHub giả lập (không gửi gì ra mạng)."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diligo import cli, publish  # noqa: E402


class FakeGitHub:
    def __init__(self, current: bytes | None):
        self.calls = []
        self.files = {"index.html": current} if current is not None else {}
        self.ref = "c0"

    def __call__(self, method, url, body):
        self.calls.append((method, url.split("/repos/o/r")[1], body))
        path = url.split("/repos/o/r")[1]
        if method == "GET" and path == "/git/ref/heads/main":
            return {"object": {"sha": self.ref}}
        if method == "GET" and path.startswith("/git/commits/"):
            return {"tree": {"sha": "t0"}}
        if method == "GET" and path.startswith("/git/trees/"):
            return {"tree": [{"path": p, "type": "blob", "sha": publish.git_blob_sha(d)} for p, d in self.files.items()]
                    + [{"path": "diligo", "type": "tree", "sha": "x"}]}
        if method == "POST" and path == "/git/blobs":
            self.pending = base64.b64decode(body["content"]); return {"sha": "b1"}
        if method == "POST" and path == "/git/trees":
            self.tree_body = body; return {"sha": "t1"}
        if method == "POST" and path == "/git/commits":
            self.commit_body = body; return {"sha": "c1abcdef"}
        if method == "PATCH" and path == "/git/refs/heads/main":
            self.ref = body["sha"]; self.files["index.html"] = self.pending; return {}
        raise AssertionError(f"gọi API ngoài dự kiến: {method} {path}")


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diligo_pub_"))
        self.cfg = {"owner": "o", "repo": "r", "branch": "main", "path": "index.html"}
        self.html = self.tmp / "index.html"
        self.html.write_text("<html><script>const DATA={\"daily\":[]};</script></html>", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_publishes_only_index_html(self):
        gh = FakeGitHub(b"old")
        changed, msg = publish.publish_index(self.html, self.cfg, gh, now=datetime(2026, 11, 12, 9, 5))
        self.assertTrue(changed)
        self.assertEqual(gh.tree_body["tree"], [{"path": "index.html", "mode": "100644", "type": "blob", "sha": "b1"}])
        self.assertEqual(gh.tree_body["base_tree"], "t0")      # giữ nguyên mọi file khác trong repo
        self.assertEqual(gh.commit_body["parents"], ["c0"])
        self.assertIn("12/11/2026 09:05", gh.commit_body["message"])
        self.assertEqual(gh.files["index.html"], self.html.read_bytes())

    def test_skips_when_unchanged(self):
        gh = FakeGitHub(self.html.read_bytes())
        changed, _ = publish.publish_index(self.html, self.cfg, gh)
        self.assertFalse(changed)
        self.assertFalse([c for c in gh.calls if c[0] != "GET"])

    def test_refuses_non_dashboard_files(self):
        other = self.tmp / "HistoryStore_v2.json"; other.write_text("{}", encoding="utf-8")
        with self.assertRaises(publish.PublishError):
            publish.publish_index(other, self.cfg, FakeGitHub(None))
        fake = self.tmp / "sub"; fake.mkdir(); (fake / "index.html").write_text("<html>khác</html>", encoding="utf-8")
        with self.assertRaises(publish.PublishError):
            publish.publish_index(fake / "index.html", self.cfg, FakeGitHub(None))

    def test_config_rules(self):
        d = self.tmp / "cfg"; d.mkdir()
        self.assertIsNone(publish.load_publish_config(d))                    # chưa cài
        (d / "GITHUB_PUBLISH.json").write_text(json.dumps(self.cfg), encoding="utf-8")
        self.assertIsNone(publish.load_publish_config(d))                    # chưa có token
        (d / "GITHUB_TOKEN.txt").write_text("﻿  github_pat_abc \n", encoding="utf-8")
        cfg, token = publish.load_publish_config(d)
        self.assertEqual(token, "github_pat_abc")
        (d / "GITHUB_PUBLISH.json").write_text(json.dumps(dict(self.cfg, path="HistoryStore_v2.json")), encoding="utf-8")
        with self.assertRaises(publish.PublishError):
            publish.load_publish_config(d)
        self.assertEqual(publish.pages_url(self.cfg), "https://o.github.io/r/")

    def test_token_file_is_gitignored(self):
        self.assertIn("GITHUB_TOKEN.txt", (ROOT / ".gitignore").read_text(encoding="utf-8").split())

    def test_publish_error_does_not_fail_the_run(self):
        out = self.tmp / "out"; out.mkdir(); (out / "index.html").write_bytes(self.html.read_bytes())
        d = self.tmp / "cfg2"; d.mkdir()
        (d / "GITHUB_PUBLISH.json").write_text(json.dumps(self.cfg), encoding="utf-8")
        (d / "GITHUB_TOKEN.txt").write_text("tok", encoding="utf-8")
        orig = publish.make_requester
        def broken(token, timeout=120):
            def req(m, u, b): raise publish.PublishError("Token sai hoặc đã hết hạn.")
            return req
        cli.make_requester = broken
        try:
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                cli.publish_step(out / "index.html", d)
        finally:
            cli.make_requester = orig
        self.assertIn("CHƯA ĐĂNG ĐƯỢC LÊN GITHUB", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
