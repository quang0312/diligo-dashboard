# -*- coding: utf-8 -*-
"""So sánh bản mới với V39 gốc trên DỮ LIỆU THẬT (không đưa lên GitHub).

Chạy khi có biến môi trường DILIGO_GOLDEN_DIR trỏ tới thư mục gồm:
    Data_Input/            file xuất từ sàn
    HistoryStore.json      kho lịch sử kiểu cũ (V30–V39)
    baseline_v25.json      dữ liệu nền của V39

Ví dụ (Windows):
    set DILIGO_GOLDEN_DIR=D:\\Diligo_Golden
    py -m unittest discover -s tests -v

Yêu cầu: index.html, toàn bộ CSV, file kiểm tra và kho lịch sử phải KHỚP TỪNG BYTE / TỪNG DÒNG
với V39, cả ở lần chạy chuyển đổi đầu tiên lẫn lần chạy tiếp theo (khi đã không cần baseline_v25.json).

Thay đổi CÓ CHỦ ĐÍCH so với V39 (bản V39 trong test được nạp đúng phần sửa này, mọi phần khác giữ nguyên):
- 40.1: đọc sheet đóng góp Live/Video/Affiliate Shopee theo mẫu mới ("Theo phiên live (...)",
  cột "Tên phiên live", cột số đơn "Orders"). V39 đọc số đơn = 0 với file xuất từ khoảng 21/09/2026.
  Thêm cảnh báo khi sheet danh sách phiên/video/KOC trong file Shopee trống.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diligo import cli  # noqa: E402

GOLDEN = os.environ.get("DILIGO_GOLDEN_DIR")
LEGACY_SCRIPT = ROOT / "tests" / "legacy_v39" / "Diligo_Auto_Dashboard_V39.py"
COMPARED_FILES = [
    "index.html", "KIEM_TRA_NAP_ADS.txt", "KIEM_TRA_NAP_TAI_CHINH.txt",
    "Data_Output/Sales_Daily.csv", "Data_Output/Overview_Period.csv", "Data_Output/Source_Period.csv",
    "Data_Output/Source_Product.csv", "Data_Output/Content.csv", "Data_Output/Shopee_Traffic_Daily.csv",
    "Data_Output/Ads.csv", "Data_Output/Finance.csv", "Data_Output/Warnings.csv",
]


# Các phần sửa có chủ đích (xem docstring): V39 dùng bộ đọc mới cho đúng phần đó.
LEGACY_PATCH = f"""
# --- vá trong test: thay đổi có chủ đích của bản 40.x ---
sys.path.insert(0, {str(ROOT)!r})
from diligo.parsers.shopee import parse_shopee_contribution  # noqa: E402,F811
"""


def strip_v1(store: dict) -> dict:
    out = {k: v for k, v in store.items() if k != "_meta"}
    out["source_periods"] = [{k: v for k, v in r.items() if k != "products"} for r in out.get("source_periods", [])]
    return out


@unittest.skipUnless(GOLDEN, "Đặt DILIGO_GOLDEN_DIR để chạy so sánh với V39 trên dữ liệu thật")
class GoldenV39(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        g = Path(GOLDEN)
        cls.tmp = Path(tempfile.mkdtemp(prefix="diligo_golden_"))
        # V39 chạy với cùng template mới để so sánh index.html từng byte (dữ liệu nhúng do Python quyết định).
        legacy = cls.tmp / "legacy"; legacy.mkdir()
        src = LEGACY_SCRIPT.read_text(encoding="utf-8")
        tail = 'if __name__=="__main__":'
        assert src.count(tail) == 1
        src = src.replace(tail, LEGACY_PATCH + tail)
        (legacy / "Diligo_Auto_Dashboard.py").write_text(src, encoding="utf-8")
        shutil.copy2(ROOT / "templates" / "dashboard.html", legacy / "dashboard_template_v25.html")
        shutil.copy2(ROOT / "AUTOMATION_CONFIG.json", legacy / "AUTOMATION_CONFIG.json")
        shutil.copy2(g / "baseline_v25.json", legacy / "baseline_v25.json")
        cls.legacy = legacy
        cls.input = g / "Data_Input"
        cls.empty_input = cls.tmp / "empty_input"; cls.empty_input.mkdir()
        cls.out_old = cls.tmp / "out_old"; cls.out_new = cls.tmp / "out_new"
        for o in (cls.out_old, cls.out_new):
            o.mkdir(); shutil.copy2(g / "HistoryStore.json", o / "HistoryStore.json")
        cls.no_baseline = cls.tmp / "no_baseline"; cls.no_baseline.mkdir()
        cls.baseline_dir = g

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_old(self, inp: Path):
        r = subprocess.run([sys.executable, "-I", str(self.legacy / "Diligo_Auto_Dashboard.py"),
                            "--input", str(inp), "--output", str(self.out_old)],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def run_new(self, inp: Path, baseline_dirs):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = cli.run(inp, self.out_new, baseline_dirs)
        self.assertEqual(rc, 0, buf.getvalue())

    def assert_same_outputs(self, label: str):
        for rel in COMPARED_FILES:
            a = (self.out_old / rel).read_bytes(); b = (self.out_new / rel).read_bytes()
            self.assertTrue(a == b, f"[{label}] {rel} khác V39 ({len(a)} vs {len(b)} bytes)")
        old = strip_v1(json.loads((self.out_old / "HistoryStore.json").read_text(encoding="utf-8")))
        new = json.loads((self.out_new / "HistoryStore_v2.json").read_text(encoding="utf-8"))
        self.assertEqual(new["schema_version"], 2)
        self.assertEqual(old, new["raw"], f"[{label}] kho raw khác V39")
        base = json.loads((self.baseline_dir / "baseline_v25.json").read_text(encoding="utf-8"))
        self.assertEqual(base, new["baseline"], f"[{label}] baseline trong kho khác baseline_v25.json")

    def test_1_migration_then_rebuild(self):
        v1_before = (self.out_new / "HistoryStore.json").read_bytes()
        # Lần 1: có file mới trong Data_Input, chuyển kho cũ + baseline sang kho v2.
        self.run_old(self.input); self.run_new(self.input, [self.baseline_dir])
        self.assert_same_outputs("lần chạy chuyển đổi")
        self.assertEqual(v1_before, (self.out_new / "HistoryStore.json").read_bytes(), "HistoryStore.json cũ bị sửa")
        # Lần 2: Data_Input trống, bản mới KHÔNG được thấy baseline_v25.json nữa: chỉ dùng kho v2.
        self.run_old(self.empty_input); self.run_new(self.empty_input, [self.no_baseline])
        self.assert_same_outputs("dựng lại từ kho, không cần baseline")
        # Lần 3: nạp lại cùng bộ file (kiểm tra thay kỳ trùng, không cộng đôi).
        self.run_old(self.input); self.run_new(self.input, [self.no_baseline])
        self.assert_same_outputs("nạp lại file trùng")
        self.assertTrue(any((self.out_new / "HistoryStore_backups").glob("*.json.gz")), "chưa tạo bản sao kho")


if __name__ == "__main__":
    unittest.main()
