# -*- coding: utf-8 -*-
"""Đăng index.html lên GitHub Pages bằng GitHub API (không cần cài Git).

Chỉ đăng DUY NHẤT file index.html vừa tạo. Không bao giờ gửi file Excel/CSV/kho lịch sử.

Cấu hình (đặt cạnh CAP_NHAT_BAO_CAO.bat):
- GITHUB_PUBLISH.json : owner / repo / branch / path (đã có sẵn, không chứa bí mật).
- GITHUB_TOKEN.txt    : token GitHub (fine-grained, chỉ cấp quyền Contents: Read and write cho
                        đúng repo này). File này nằm trong .gitignore, không bao giờ được đẩy lên.
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

CONFIG_FILENAME = "GITHUB_PUBLISH.json"
TOKEN_FILENAME = "GITHUB_TOKEN.txt"
API = "https://api.github.com"
ALLOWED_PATH = "index.html"   # chặn cứng: chỉ được ghi đúng file này trong repo
MARKER = "const DATA="        # dấu hiệu đây đúng là file dashboard do chương trình tạo


class PublishError(RuntimeError):
    pass


def load_publish_config(config_dir: Path) -> tuple[dict, str] | None:
    """Trả về (config, token) hoặc None nếu chưa cài đặt đăng báo cáo."""
    cpath = config_dir / CONFIG_FILENAME
    tpath = config_dir / TOKEN_FILENAME
    if not cpath.exists() or not tpath.exists():
        return None
    try:
        cfg = json.loads(cpath.read_text(encoding="utf-8"))
    except Exception as e:
        raise PublishError(f"{CONFIG_FILENAME} sai cú pháp JSON: {e}") from e
    for k in ("owner", "repo", "branch"):
        if not str(cfg.get(k) or "").strip():
            raise PublishError(f"{CONFIG_FILENAME} thiếu '{k}'")
    cfg.setdefault("path", ALLOWED_PATH)
    if cfg["path"] != ALLOWED_PATH:
        raise PublishError(f"{CONFIG_FILENAME}: chỉ được đăng '{ALLOWED_PATH}', không đăng '{cfg['path']}'")
    token = tpath.read_text(encoding="utf-8-sig").strip()
    if not token or token.startswith("DAN_TOKEN"):
        return None
    return cfg, token


def read_repo_config(config_dir: Path) -> dict | None:
    """Đọc GITHUB_PUBLISH.json (không cần token). Dùng cho cách đăng thủ công."""
    p = config_dir / CONFIG_FILENAME
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not all(str(cfg.get(k) or "").strip() for k in ("owner", "repo", "branch")):
        return None
    return cfg


def upload_url(cfg: dict) -> str:
    return f"https://github.com/{cfg['owner']}/{cfg['repo']}/upload/{cfg['branch']}"


def open_manual_upload(html_path: Path, cfg: dict) -> bool:
    """Windows: mở trang tải file của GitHub + mở thư mục và chọn sẵn index.html."""
    import subprocess
    import sys
    import webbrowser
    if sys.platform != "win32":
        return False
    try:
        webbrowser.open(upload_url(cfg))
        subprocess.Popen(["explorer", "/select,", str(html_path)])
        return True
    except Exception:
        return False


def pages_url(cfg: dict) -> str:
    owner, repo = cfg["owner"], cfg["repo"]
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


Requester = Callable[[str, str, dict | None], dict]


def make_requester(token: str, timeout: int = 120) -> Requester:
    def request(method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "diligo-dashboard-publisher",
            **({"Content-Type": "application/json"} if data is not None else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            msg = {
                401: "Token sai hoặc đã hết hạn. Tạo token mới và dán vào GITHUB_TOKEN.txt.",
                403: "Token không đủ quyền. Cần quyền 'Contents: Read and write' cho repo này.",
                404: "Không tìm thấy repo/nhánh, hoặc token chưa được cấp quyền cho repo này.",
                409: "Repo đang có thay đổi khác cùng lúc. Chạy lại BAT.",
                422: "GitHub từ chối dữ liệu gửi lên. Chạy lại BAT; nếu vẫn lỗi, gửi ảnh màn hình.",
            }.get(e.code, f"GitHub trả lỗi {e.code}.")
            raise PublishError(msg) from e
        except urllib.error.URLError as e:
            raise PublishError(f"Không kết nối được GitHub (kiểm tra mạng): {e.reason}") from e
    return request


def publish_index(html_path: Path, cfg: dict, request: Requester, now: datetime | None = None) -> tuple[bool, str]:
    """Đẩy html_path lên repo thành `index.html`. Trả về (đã_đăng_mới, thông_báo).
    Nếu nội dung giống hệt bản đang có trên GitHub thì không tạo commit mới."""
    data = html_path.read_bytes()
    if html_path.name != ALLOWED_PATH or MARKER.encode() not in data[:500000]:
        raise PublishError(f"Từ chối đăng {html_path}: không phải file dashboard index.html.")
    base = f"{API}/repos/{cfg['owner']}/{cfg['repo']}"
    branch, path = cfg["branch"], ALLOWED_PATH

    head_sha = request("GET", f"{base}/git/ref/heads/{branch}", None)["object"]["sha"]
    tree_sha = request("GET", f"{base}/git/commits/{head_sha}", None)["tree"]["sha"]
    tree = request("GET", f"{base}/git/trees/{tree_sha}", None).get("tree", [])
    current = next((t.get("sha") for t in tree if t.get("path") == path and t.get("type") == "blob"), None)
    if current == git_blob_sha(data):
        return False, "Báo cáo trên GitHub đã giống bản vừa tạo, không cần đăng lại."

    blob = request("POST", f"{base}/git/blobs", {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
    new_tree = request("POST", f"{base}/git/trees", {
        "base_tree": tree_sha,
        "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
    })
    stamp = (now or datetime.now()).strftime("%d/%m/%Y %H:%M")
    commit = request("POST", f"{base}/git/commits", {
        "message": f"Cập nhật báo cáo {stamp}", "tree": new_tree["sha"], "parents": [head_sha],
    })
    request("PATCH", f"{base}/git/refs/heads/{branch}", {"sha": commit["sha"], "force": False})
    return True, f"Đã đăng bản {stamp} (commit {commit['sha'][:7]})."
