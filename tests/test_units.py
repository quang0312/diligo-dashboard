# -*- coding: utf-8 -*-
"""Test nhanh, không cần dữ liệu thật: chạy được trên mọi máy.

    py -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diligo import cli, store  # noqa: E402
from diligo.config import BACKUP_KEEP  # noqa: E402
from diligo.dashboard import STATE_PLACEHOLDER, TEMPLATE_FILE, build_dashboard_data, render_html  # noqa: E402
from diligo.utils import dedup_by_period, parse_date_any, parse_period_text, period_from_filename, safe_float, safe_pct  # noqa: E402
from diligo.xlsx import xlsx_read_sheet  # noqa: E402


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="diligo_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class UtilsTest(unittest.TestCase):
    def test_vietnamese_numbers(self):
        self.assertEqual(safe_float("1.234.567"), 1234567.0)
        self.assertEqual(safe_float("1.234,5"), 1234.5)
        self.assertEqual(safe_float("₫1.000"), 1000.0)
        self.assertEqual(safe_float("-"), 0.0)
        self.assertEqual(safe_float(None), 0.0)
        self.assertEqual(safe_float(3.5), 3.5)
        self.assertAlmostEqual(safe_pct("12,5%"), 0.125)

    def test_dates_and_periods(self):
        self.assertEqual(parse_date_any("15/09/2026"), date(2026, 9, 15))
        self.assertEqual(parse_date_any("2026-09-15"), date(2026, 9, 15))
        self.assertEqual(parse_period_text("01/09/2026 - 30/09/2026"), (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(parse_period_text("2026-09-15 ~ 2026-09-15"), (date(2026, 9, 15), date(2026, 9, 15)))
        self.assertEqual(period_from_filename("producttraffic_Product_Card.20260901_20260930.xlsx"),
                         (date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual(period_from_filename("Products Card List_20260915.xlsx"), (date(2026, 9, 15), date(2026, 9, 15)))

    def test_dedup_keeps_newest_file(self):
        rows = [{"platform": "Shopee", "date": "2026-09-15", "gmv": 1, "_mtime": 10},
                {"platform": "Shopee", "date": "2026-09-15", "gmv": 2, "_mtime": 20},
                {"platform": "TikTok", "date": "2026-09-15", "gmv": 3, "_mtime": 5}]
        out = dedup_by_period(rows, ("platform", "date"))
        self.assertEqual(sorted(r["gmv"] for r in out), [2, 3])


class XlsxReaderTest(TempDirCase):
    def make_xlsx(self) -> Path:
        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        p = self.tmp / "t.xlsx"
        with ZipFile(p, "w") as z:
            z.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
                       f'<sheet name="Tổng quan" sheetId="1" r:id="rId1"/><sheet name="(đơn đã xác nhận) Nguồn" sheetId="2" r:id="rId2"/></sheets></workbook>')
            z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
            z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{main}"><si><t>Ngày</t></si><si><t>Doanh số</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{main}"><sheetData>'
                       '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
                       '<row r="2"><c r="A2" t="inlineStr"><is><t>15/09/2026</t></is></c><c r="C2"><v>1234.5</v></c></row>'
                       '</sheetData></worksheet>')
            z.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{main}"><sheetData><row r="1"><c r="B1" t="b"><v>1</v></c></row></sheetData></worksheet>')
        return p

    def test_read_by_index_name_and_selector(self):
        p = self.make_xlsx()
        name, rows = xlsx_read_sheet(p, 0)
        self.assertEqual(name, "Tổng quan")
        self.assertEqual(rows, [["Ngày", None, "Doanh số"], ["15/09/2026", None, "1234.5"]])
        self.assertEqual(xlsx_read_sheet(p, "nguồn")[1], [[None, True]])
        self.assertEqual(xlsx_read_sheet(p, lambda n, i, alln: "xác nhận" in n)[0], "(đơn đã xác nhận) Nguồn")
        with self.assertRaises(ValueError):
            xlsx_read_sheet(p, "không có")


class ShopeeContributionTest(TempDirCase):
    """Shopee đổi mẫu file Live/Video từ 10/2026; phải đọc được cả mẫu cũ và mẫu mới."""
    def make(self, name: str, sheets: list[tuple[str, list[list[str]]]]) -> Path:
        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        from xml.sax.saxutils import escape
        p = self.tmp / name
        with ZipFile(p, "w") as z:
            z.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>' + "".join(
                f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, (n, _) in enumerate(sheets)) + "</sheets></workbook>")
            z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
                f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets))) + "</Relationships>")
            for i, (_, rows) in enumerate(sheets):
                body = "".join("<row>" + "".join(f'<c r="{chr(65 + j)}{r + 1}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                                                 for j, v in enumerate(row)) + "</row>" for r, row in enumerate(rows))
                z.writestr(f"xl/worksheets/sheet{i + 1}.xml", f'<worksheet xmlns="{main}"><sheetData>{body}</sheetData></worksheet>')
        return p

    def live_sheets(self, names, title_col, orders_col):
        head = ["Mã Phiên Chat", title_col, "Tỷ lệ doanh số", "Doanh số (VND)", orders_col, "Sản phẩm", "Lượt xem Livestream", "Lượt nhấp vào sản phẩm"]
        return [("(đơn đã xác nhận)Lưu lượng ...", [["Mã sản phẩm", "Doanh số (VND)"], ["1", "999"]])] + [
            (n, [["Live"], head, ["42113202", "Deal 9.10", "9%", gmv, orders, "224,00", "994", "868"]])
            for n, gmv, orders in zip(names, ["20.181.890", "18.417.546", "17.559.722"], ["161,00", "148,00", "142,00"])]

    def check_live(self, p: Path):
        from diligo.parsers.shopee import parse_shopee_contribution
        w = []
        c = parse_shopee_contribution(p, "live", w)
        self.assertEqual(w, [])
        self.assertEqual((c["period_start"], c["period_end"]), ("2026-10-01", "2026-10-31"))
        it = c["items"][0]
        self.assertEqual((it["item_id"], it["title"], it["gmv"], it["orders"], it["units"], it["views"]),
                         ("42113202", "Deal 9.10", 18417546.0, 148.0, 224.0, 994.0))   # luôn lấy "đơn đã xác nhận"

    def test_new_format_oct_2026(self):
        self.check_live(self.make("producttraffic_Seller_Live.20261001_20261031.xlsx", self.live_sheets(
            ["Theo phiên live (đã đặt hàng)", "Theo phiên live (đơn đã xác...", "Theo phiên live (đơn đã tha..."],
            "Tên phiên live", "Orders")))

    def test_old_format(self):
        self.check_live(self.make("producttraffic_Seller_Live.20261001_20261031.xlsx", self.live_sheets(
            ["Session Contribution (place...", "Session Contribution (confi...", "Session Contribution (paid ..."],
            "Session Title", "psd_label_orders")))

class MergeTest(unittest.TestCase):
    def test_new_period_replaces_old_not_added(self):
        old = store._empty_store(); new = store._empty_store()
        old["daily"] = [{"platform": "Shopee", "date": "2026-09-15", "gmv": 100},
                        {"platform": "Shopee", "date": "2026-09-14", "gmv": 50}]
        new["daily"] = [{"platform": "Shopee", "date": "2026-09-15", "gmv": 120}]
        out = store.merge_history_store(old, new)
        self.assertEqual([(r["date"], r["gmv"]) for r in out["daily"]], [("2026-09-14", 50), ("2026-09-15", 120)])

    def test_reimported_source_period_replaces_all_products(self):
        k = {"platform": "Shopee", "source": "Video", "period_start": "2026-09-01", "period_end": "2026-09-30"}
        old = store._empty_store(); new = store._empty_store()
        old["product_facts"] = [dict(k, product_id="A", product_name="A", source_file="cu.xlsx", gmv=1),
                                dict(k, product_id="B", product_name="B", source_file="cu.xlsx", gmv=2)]
        new["source_periods"] = [dict(k, gmv=5, source_file="moi.xlsx")]
        new["product_facts"] = [dict(k, product_id="A", product_name="A", source_file="moi.xlsx", gmv=5)]
        out = store.merge_history_store(old, new)
        self.assertEqual([(r["product_id"], r["gmv"]) for r in out["product_facts"]], [("A", 5)])

    def test_ads_replaced_per_family_and_period(self):
        base = {"platform": "Shopee", "subtype": "Shopee Ads", "period_start": "2026-10-01", "period_end": "2026-10-31"}
        old = store._empty_store(); new = store._empty_store()
        old["ads"] = [dict(base, campaign="X", cost=1, source_file="a.csv"), dict(base, campaign="Y", cost=2, source_file="a.csv")]
        new["ads"] = [dict(base, campaign="X", cost=3, source_file="b.csv")]
        out = store.merge_history_store(old, new)
        self.assertEqual([(r["campaign"], r["cost"]) for r in out["ads"]], [("X", 3)])


class StoreTest(TempDirCase):
    def baseline(self):
        return {"daily": [{"platform": "Shopee", "date": "2026-08-01", "gmv": 9}], "products": []}

    def test_first_run_refuses_without_baseline_if_old_history_exists(self):
        out = self.tmp / "out"; out.mkdir()
        (out / "HistoryStore.json").write_text(json.dumps({"daily": [{"platform": "Shopee", "date": "2026-09-15"}]}), encoding="utf-8")
        with self.assertRaises(store.StoreError):
            store.load_store(out, [self.tmp / "khong_co"])
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli.run(self.tmp, out, [self.tmp / "khong_co"])
        self.assertEqual(rc, 3)
        self.assertFalse((out / "HistoryStore_v2.json").exists())
        self.assertFalse((out / "index.html").exists())

    def test_migration_keeps_old_files_and_roundtrips(self):
        out = self.tmp / "out"; out.mkdir(); bdir = self.tmp / "b"; bdir.mkdir()
        v1 = {"daily": [{"platform": "Shopee", "date": "2026-09-15", "gmv": 1}],
              "source_periods": [{"platform": "Shopee", "source": "Video", "period_start": "2026-09-15", "period_end": "2026-09-15",
                                  "gmv": 1, "products": [{"product_id": "A"}]}],
              "_meta": {"x": 1}}
        (out / "HistoryStore.json").write_text(json.dumps(v1), encoding="utf-8")
        (bdir / "baseline_v25.json").write_text(json.dumps(self.baseline()), encoding="utf-8")
        before = (out / "HistoryStore.json").read_bytes()
        s, notes = store.load_store(out, [bdir])
        self.assertEqual(s["baseline"], self.baseline())
        self.assertNotIn("products", s["raw"]["source_periods"][0])
        store.save_store(out, s["raw"], s["baseline"])
        self.assertEqual(before, (out / "HistoryStore.json").read_bytes())
        s2, notes2 = store.load_store(out, [self.tmp / "khong_co"])  # lần sau không cần baseline_v25.json
        self.assertEqual(s2, s); self.assertEqual(notes2, [])

    def test_backups_rotate(self):
        out = self.tmp / "out"
        for i in range(BACKUP_KEEP + 3):
            raw = store._empty_store(); raw["daily"] = [{"platform": "Shopee", "date": f"2026-09-{i + 1:02d}"}]
            store.save_store(out, raw, {})
        backups = sorted((out / "HistoryStore_backups").glob("*.json.gz"))
        self.assertEqual(len(backups), BACKUP_KEEP)
        last = json.loads(gzip.decompress(backups[-1].read_bytes()))
        self.assertEqual(last["raw"]["daily"][0]["date"], f"2026-09-{BACKUP_KEEP + 2:02d}")


class DashboardTest(unittest.TestCase):
    def test_raw_wins_over_baseline_for_same_day(self):
        baseline = {"daily": [{"platform": "Shopee", "date": "2026-09-15", "gmv": 1},
                              {"platform": "Shopee", "date": "2026-08-01", "gmv": 7}]}
        raw = store._empty_store(); raw["daily"] = [{"platform": "Shopee", "date": "2026-09-15", "gmv": 2}]
        data = build_dashboard_data(raw, json.loads(json.dumps(baseline)))
        self.assertEqual([(r["date"], r["gmv"]) for r in data["daily"]], [("2026-08-01", 7), ("2026-09-15", 2)])

    def test_render_sets_default_period_and_config(self):
        data = {"daily": [{"date": "2026-10-01"}, {"date": "2026-10-15"}]}
        html = render_html(data, {"owners": {}, "deadlines": {}, "peak_share": 0.5}, ("2026-10-01", "2026-10-15"))
        self.assertNotIn("__DATA__", html); self.assertNotIn("__AUTO_CONFIG__", html)
        self.assertIn("from:'2026-10-01',to:'2026-10-15'", html)


class TemplateTest(unittest.TestCase):
    def setUp(self):
        self.t = TEMPLATE_FILE.read_text(encoding="utf-8")

    def test_placeholders_and_reset_button(self):
        for s in ("__DATA__", "__AUTO_CONFIG__", STATE_PLACEHOLDER, 'id="resetFilters"', "function resetFilters()",
                  "const DEFAULT_VIEW=Object.assign({},state);"):
            self.assertIn(s, self.t)

    def test_no_hardcoded_business_numbers(self):
        import re
        self.assertEqual(re.findall(r"\d{1,3}(?:\.\d{3}){2,}", self.t), [])

    @unittest.skipUnless(shutil.which("node"), "cần Node.js để kiểm tra cú pháp JavaScript")
    def test_javascript_syntax(self):
        script = self.t[self.t.index("<script>") + 8:self.t.rindex("</script>")]
        script = script.replace("__DATA__", "{}").replace("__AUTO_CONFIG__", "{}")
        r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"],
                           input=script, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
