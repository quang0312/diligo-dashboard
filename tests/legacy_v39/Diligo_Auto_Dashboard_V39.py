# -*- coding: utf-8 -*-
r"""
DILIGO AUTO DASHBOARD V31 · SO SÁNH KỲ
=====================
Không cần pandas/openpyxl. Script chỉ dùng thư viện chuẩn của Python.

Luồng sử dụng:
    D:\\Data_Input  -> chạy script -> D:\\Diligo_Dashboard_Output\\index.html

Mỗi lần cập nhật:
1) Tải file raw mới từ Shopee / TikTok.
2) Bỏ đúng vào các folder trong D:\Data_Input (giữ nguyên tên file gốc).
3) Chạy CAP_NHAT_BAO_CAO.bat hoặc:
       py Diligo_Auto_Dashboard.py
4) Script ghi dữ liệu mới vào D:\Diligo_Dashboard_Output\HistoryStore.json.
5) Khi đã thấy dòng ✅ XONG, có thể xóa raw trong Data_Input; lần sau lịch sử vẫn còn.
6) Mở index.html mới. Nếu dùng GitHub Pages, thay file index.html trong repo bằng file mới.

Nguyên tắc dữ liệu đã cài sẵn:
- Shopee bán hàng: dùng Đơn đã xác nhận.
- Nguồn bán hàng: Sàn -> Nguồn -> Ngành hàng -> Sản phẩm.
- Contribution tách riêng để Top Video / Top Live / Top Affiliate.
- TikTok không dùng ngày đăng video làm ngày hiệu suất; dùng phạm vi báo cáo.
- Khách hàng unique không cộng dồn theo ngày cho khoảng nhiều ngày.
- Ads tách khỏi nguồn bán hàng; Shopee không cộng GMV attribution chồng làm headline.
- Finance dùng ngày quyết toán, không phải ngày đặt hàng.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import shutil
import sys
import traceback
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zipfile import ZipFile
import xml.etree.ElementTree as ET

# -------------------------
# CẤU HÌNH MẶC ĐỊNH
# -------------------------
DEFAULT_INPUT = Path(r"D:\Data_Input")
DEFAULT_OUTPUT = Path(r"D:\Diligo_Dashboard_Output")
HISTORY_FILENAME = "HistoryStore.json"
HISTORY_BACKUP_FILENAME = "HistoryStore_BACKUP.json"

SHOPEE_MIXED_OVERRIDES = {
    "22488621592": ("Lipzo", "Kem đánh răng"),
    "20744336169": ("Lipzo", "Kem đánh răng"),
    "24551015559": ("Lipzo", "Kem đánh răng"),
}
TIKTOK_MIXED_OVERRIDES = {
    "1731356952881497997": ("Lipzo", "Kem đánh răng"),
}

SOURCE_ORDER = ["Thẻ sản phẩm", "Phát trực tiếp", "Video", "Tiếp thị liên kết"]
CATEGORY_ORDER = [
    "Bàn chải", "Bàn chải điện", "Kem đánh răng", "Nước súc miệng",
    "Bông trang điểm", "Tăm bông", "Bông viên", "Bông tẩm cồn",
    "Khăn", "Khăn giấy", "Khẩu trang", "CHƯA GÁN", "Đa ngành / chưa phân bổ"
]

# -------------------------
# TIỆN ÍCH CHUNG
# -------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


def safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        if math.isnan(v) if isinstance(v, float) else False:
            return 0.0
        return float(v)
    s = str(v).strip()
    if s in {"", "-", "/", "N/A", "n/a", "None", "null", "nan"}:
        return 0.0
    s = s.replace("₫", "").replace("VND", "").replace(" ", "")
    # Chuẩn Việt: 145.809,51 -> 145809.51
    # Chuẩn Ads/TikTok: 83152.000 -> 83152.000 (dấu . là decimal)
    # Heuristic: nếu có cả . và , => . nghìn, , thập phân
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Nếu dạng 7.956 từ Shopee locale -> có thể là 7956.
        # Chỉ coi là nghìn khi phần sau dấu chấm đúng 3 số và phần trước <= 3 số,
        # ngoại trừ Ads/ROAS được gọi qua safe_float_dot().
        if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", s):
            s = s.replace(".", "")
    try:
        return float(s)
    except Exception:
        return 0.0


def safe_float_dot(v: Any) -> float:
    """Số kiểu Ads/TikTok: dấu chấm là thập phân, không phải phân cách nghìn."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("₫", "").replace("VND", "").replace(" ", "")
    if s in {"", "-", "/", "N/A", "n/a"}:
        return 0.0
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def safe_int(v: Any) -> int:
    return int(round(safe_float(v)))


def safe_pct(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        n = float(v)
        return n / 100 if abs(n) > 1 else n
    s = str(v).strip()
    if s in {"", "-", "/", "N/A", "n/a"}:
        return 0.0
    has_pct = "%" in s
    s = s.replace("%", "").strip()
    n = safe_float(s)
    return n / 100 if has_pct or abs(n) > 1 else n


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def parse_date_any(s: Any) -> date | None:
    if s is None:
        return None
    text = str(s).strip()
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            pass
    m = re.search(r"(20\d{2})[-_/](\d{2})[-_/](\d{2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    m = re.search(r"(\d{2})[-_/](\d{2})[-_/](20\d{2})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except Exception:
            pass
    return None


def parse_period_text(text: Any) -> tuple[date | None, date | None]:
    s = str(text or "")
    # yyyy-mm-dd ~ yyyy-mm-dd or yyyy/mm/dd-yyyy/mm/dd
    ms = re.findall(r"(20\d{2})[-/](\d{2})[-/](\d{2})", s)
    if len(ms) >= 2:
        a = date(int(ms[0][0]), int(ms[0][1]), int(ms[0][2]))
        b = date(int(ms[1][0]), int(ms[1][1]), int(ms[1][2]))
        return a, b
    # dd-mm-yyyy - dd-mm-yyyy
    ms = re.findall(r"(\d{2})[-/](\d{2})[-/](20\d{2})", s)
    if len(ms) >= 2:
        a = date(int(ms[0][2]), int(ms[0][1]), int(ms[0][0]))
        b = date(int(ms[1][2]), int(ms[1][1]), int(ms[1][0]))
        return a, b
    if len(ms) == 1:
        a = date(int(ms[0][2]), int(ms[0][1]), int(ms[0][0]))
        return a, a
    return None, None


def period_from_filename(name: str) -> tuple[date | None, date | None]:
    # YYYYMMDD_YYYYMMDD
    m = re.search(r"(20\d{6})[_-](20\d{6})", name)
    if m:
        return (
            datetime.strptime(m.group(1), "%Y%m%d").date(),
            datetime.strptime(m.group(2), "%Y%m%d").date(),
        )
    # 15_09_2026-15_09_2026
    m = re.search(r"(\d{2})_(\d{2})_(20\d{2})[-_](\d{2})_(\d{2})_(20\d{2})", name)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    # 2026-09-15 00 ~ 2026-09-15 23
    ms = re.findall(r"(20\d{2})-(\d{2})-(\d{2})", name)
    if len(ms) >= 2:
        return date(*map(int, ms[0])), date(*map(int, ms[1]))
    # single YYYYMMDD in name
    m = re.search(r"(20\d{6})", name)
    if m:
        d = datetime.strptime(m.group(1), "%Y%m%d").date()
        return d, d
    return None, None


def daterange(a: date, b: date) -> list[date]:
    out = []
    d = a
    while d <= b:
        out.append(d)
        d += timedelta(days=1)
    return out


def duration_days(a: str, b: str) -> int:
    da = date.fromisoformat(a)
    db = date.fromisoformat(b)
    return (db - da).days + 1


def dedup_by_period(records: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Nếu user tải trùng cùng dataset/kỳ, giữ file mới hơn (mtime lớn hơn)."""
    best: dict[tuple, dict] = {}
    for r in records:
        k = tuple(r.get(x) for x in keys)
        old = best.get(k)
        if old is None or r.get("_mtime", 0) >= old.get("_mtime", 0):
            best[k] = r
    return list(best.values())


def unique_headers(headers: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, h in enumerate(headers):
        base = str(h).strip() if h not in (None, "") else f"Column{i+1}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(base if n == 0 else f"{base}_{n}")
    return out


def row_to_dict(headers: list[str], row: list[Any]) -> dict[str, Any]:
    return {headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}


def find_header_row(rows: list[list[Any]], required: Iterable[str]) -> int | None:
    req = [x.lower() for x in required]
    for i, row in enumerate(rows):
        vals = [str(x).strip().lower() for x in row if x not in (None, "")]
        joined = " | ".join(vals)
        if all(x in joined for x in req):
            return i
    return None


def last_numeric_in_row(row: list[Any]) -> float:
    for v in reversed(row):
        if v not in (None, ""):
            n = safe_float_dot(v)
            if n != 0 or str(v).strip() in {"0", "0.0", "0.00"}:
                return n
    return 0.0


# -------------------------
# XLSX READER THUẦN PYTHON
# -------------------------
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_num(ref: str) -> int:
    m = re.match(r"([A-Z]+)", ref or "A1")
    s = m.group(1) if m else "A"
    x = 0
    for ch in s:
        x = x * 26 + ord(ch) - 64
    return x


def xlsx_sheets(path: Path) -> list[tuple[str, str]]:
    with ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        sheets = []
        for s in wb.find(f"{{{NS_MAIN}}}sheets"):
            rid = s.attrib[f"{{{NS_REL}}}id"]
            target = relmap[rid]
            if target.startswith("/"):
                target = target.lstrip("/")
            else:
                target = "xl/" + target.lstrip("/")
            sheets.append((s.attrib["name"], target))
        return sheets


def xlsx_read_sheet(path: Path, selector: Callable[[str, int, list[str]], bool] | str | int = 0) -> tuple[str, list[list[Any]]]:
    with ZipFile(path) as z:
        # shared strings
        strings: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(f"{{{NS_MAIN}}}si"):
                strings.append("".join((t.text or "") for t in si.iter(f"{{{NS_MAIN}}}t")))

        sheets = xlsx_sheets(path)
        names = [x[0] for x in sheets]
        chosen = None
        if isinstance(selector, int):
            chosen = sheets[selector]
        elif isinstance(selector, str):
            for item in sheets:
                if item[0] == selector:
                    chosen = item
                    break
            if chosen is None:
                for item in sheets:
                    if selector.lower() in item[0].lower():
                        chosen = item
                        break
        else:
            for i, item in enumerate(sheets):
                if selector(item[0], i, names):
                    chosen = item
                    break
        if chosen is None:
            raise ValueError(f"Không tìm thấy sheet phù hợp trong {path.name}: {names}")

        name, target = chosen
        root = ET.fromstring(z.read(target))
        rows_out: list[list[Any]] = []
        for row in root.findall(f".//{{{NS_MAIN}}}sheetData/{{{NS_MAIN}}}row"):
            vals: dict[int, Any] = {}
            for c in row.findall(f"{{{NS_MAIN}}}c"):
                ref = c.attrib.get("r", "A1")
                idx = _col_num(ref)
                t = c.attrib.get("t")
                v = c.find(f"{{{NS_MAIN}}}v")
                isel = c.find(f"{{{NS_MAIN}}}is")
                val: Any = None
                if t == "s" and v is not None:
                    try:
                        val = strings[int(v.text)]
                    except Exception:
                        val = None
                elif t == "inlineStr" and isel is not None:
                    val = "".join((x.text or "") for x in isel.iter(f"{{{NS_MAIN}}}t"))
                elif t == "b" and v is not None:
                    val = v.text == "1"
                elif v is not None:
                    val = v.text
                vals[idx] = val
            if vals:
                maxc = max(vals)
                rows_out.append([vals.get(i) for i in range(1, maxc + 1)])
            else:
                rows_out.append([])
        return name, rows_out


# -------------------------
# TAXONOMY
# -------------------------
def normalize_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def classify_product(product_id: Any, name: Any, platform: str) -> tuple[str, str]:
    pid = str(product_id or "").strip().replace(".0", "")
    override = SHOPEE_MIXED_OVERRIDES if platform == "Shopee" else TIKTOK_MIXED_OVERRIDES
    if pid in override:
        return override[pid]

    t = normalize_text(name)
    brand = "Lipzo" if "lipzo" in t else ("Niva" if "niva" in t else "CHƯA GÁN")

    if "bàn chải điện" in t or "ban chai dien" in t or "sonic" in t:
        category = "Bàn chải điện"
    elif "bàn chải" in t or "ban chai" in t:
        category = "Bàn chải"
    elif "kem đánh răng" in t or "kem danh rang" in t:
        category = "Kem đánh răng"
    elif "nước súc miệng" in t or "nuoc suc mieng" in t:
        category = "Nước súc miệng"
    elif "bông tẩm cồn" in t or "bong tam con" in t:
        category = "Bông tẩm cồn"
    elif "bông viên" in t or "bong vien" in t or "bông gòn viên" in t or "bong gon vien" in t:
        category = "Bông viên"
    elif "bông tẩy trang" in t or "bông trang điểm" in t or "bong tay trang" in t or "bong trang diem" in t:
        category = "Bông trang điểm"
    elif "tăm bông" in t or "tam bong" in t:
        category = "Tăm bông"
    elif "khăn giấy" in t or "khan giay" in t:
        category = "Khăn giấy"
    elif "khăn ướt" in t or "khan uot" in t or "khăn" in t or "khan" in t:
        category = "Khăn"
    elif "khẩu trang" in t or "khau trang" in t:
        category = "Khẩu trang"
    else:
        category = "CHƯA GÁN"

    # Danh mục thương hiệu của Diligo hiện tại tách khá rõ: oral care = Lipzo; cotton/wipes/mask = Niva.
    # Chỉ dùng fallback này khi tên không ghi brand.
    if brand == "CHƯA GÁN":
        if category in {"Bàn chải", "Bàn chải điện", "Kem đánh răng", "Nước súc miệng"}:
            brand = "Lipzo"
        elif category in {"Bông trang điểm", "Tăm bông", "Bông viên", "Bông tẩm cồn", "Khăn", "Khăn giấy", "Khẩu trang"}:
            brand = "Niva"
    return brand, category


def parse_tiktok_products(cell: Any) -> list[tuple[str, str]]:
    text = str(cell or "")
    pairs = []
    for m in re.finditer(r"([^()]*)\((\d{10,})\)", text):
        nm = m.group(1).strip(" ,")
        pid = m.group(2)
        pairs.append((pid, nm))
    return pairs


# -------------------------
# PARSE SHOPEE
# -------------------------
def parse_shopee_overview(path: Path, warnings: list[str]) -> tuple[list[dict], dict | None]:
    try:
        _, rows = xlsx_read_sheet(path, lambda n, i, alln: "đơn đã xác nhận" in n.lower() and "lưu lượng" not in n.lower())
    except Exception as e:
        warnings.append(f"Shopee Overview lỗi {path.name}: {e}")
        return [], None
    if len(rows) < 2:
        return [], None
    headers = unique_headers(rows[0])
    total = row_to_dict(headers, rows[1])
    ps, pe = parse_period_text(total.get("Ngày"))
    if not ps:
        ps, pe = period_from_filename(path.name)
    if not ps:
        warnings.append(f"Không đọc được ngày Shopee Overview: {path.name}")
        return [], None

    def make(rec: dict, d: date) -> dict:
        return {
            "platform": "Shopee", "date": d.isoformat(),
            "gmv": safe_float(rec.get("Tổng doanh số (VND)")),
            "orders": safe_float(rec.get("Tổng số đơn hàng")),
            "sku_orders": safe_float(rec.get("Tổng số đơn hàng")),
            "customers": safe_float(rec.get("số người mua")) if rec.get("số người mua") not in (None, "") else None,
            "units": None,
            "refund": safe_float(rec.get("Doanh số các đơn Trả hàng/Hoàn tiền")),
            "cancel_gmv": safe_float(rec.get("Doanh số đơn hủy")),
            "revenue": safe_float(rec.get("Doanh số không bao gồm trợ giá bởi Shopee")),
            "page_views": None,
            "visitors": safe_float(rec.get("Số lượt truy cập")),
            "cvr": safe_pct(rec.get("Tỷ lệ chuyển đổi đơn hàng")),
            "product_impressions": None,
            "product_clicks": safe_float(rec.get("Lượt nhấp vào sản phẩm")),
            "aov": safe_float(rec.get("Doanh số trên mỗi đơn hàng")),
            "live_aff": 0, "live_seller": 0, "video_aff": 0, "video_seller": 0,
            "cancel_orders": safe_float(rec.get("Đơn đã hủy")),
            "refund_orders": safe_float(rec.get("Đơn đã hoàn trả / hoàn tiền")),
            "source_file": path.name,
            "_mtime": path.stat().st_mtime,
        }

    daily: list[dict] = []
    # Nếu file 1 ngày, dùng dòng tổng để tránh cộng hourly unique.
    if ps == pe:
        daily.append(make(total, ps))
    else:
        # Multi-day: tìm các dòng ngày (không có ':') sau header lặp.
        for row in rows[2:]:
            if not row or row[0] in (None, "", "Ngày"):
                continue
            s = str(row[0]).strip()
            if ":" in s:
                continue
            d = parse_date_any(s)
            if not d:
                continue
            rec = row_to_dict(headers, row)
            daily.append(make(rec, d))
        if not daily:
            warnings.append(f"Shopee Overview {path.name} là kỳ nhiều ngày nhưng không có daily rows; chỉ dùng summary kỳ.")

    summary = {
        "platform": "Shopee", "period_start": iso(ps), "period_end": iso(pe),
        "gmv": safe_float(total.get("Tổng doanh số (VND)")),
        "orders": safe_float(total.get("Tổng số đơn hàng")),
        "sku_orders": safe_float(total.get("Tổng số đơn hàng")),
        "customers": safe_float(total.get("số người mua")),
        "cvr": safe_pct(total.get("Tỷ lệ chuyển đổi đơn hàng")),
        "refund": safe_float(total.get("Doanh số các đơn Trả hàng/Hoàn tiền")),
        "cancel_gmv": safe_float(total.get("Doanh số đơn hủy")),
        "cancel_orders": safe_float(total.get("Đơn đã hủy")),
        "refund_orders": safe_float(total.get("Đơn đã hoàn trả / hoàn tiền")),
        "source_file": path.name, "_mtime": path.stat().st_mtime,
    }
    return daily, summary


SHOPEE_TRAFFIC_MAIN = {
    "Thẻ sản phẩm": "Product Card",
    "Live": "Live",
    "Video": "Video",
    "Tiếp thị liên kết": "Affiliate",
}


def parse_shopee_traffic_daily(path: Path, warnings: list[str]) -> list[dict]:
    """Đọc sheet (đơn đã xác nhận) Theo nguồn lưu lượng ở cấp ngày.

    Dữ liệu này là lớp con bên trong 4 nguồn doanh số Shopee. Ta giữ các số gốc
    theo ngày rồi tính lại tỷ trọng / CTR / CVR / AOV trong HTML cho khoảng ngày
    người dùng chọn, tránh dùng tỷ lệ tổng kỳ sai khi cắt ngày.
    """
    try:
        _, rows = xlsx_read_sheet(
            path,
            lambda n, i, alln: "đơn đã xác nhận" in n.lower() and "theo nguồn" in n.lower(),
        )
    except Exception as e:
        warnings.append(f"Shopee nguồn lưu lượng lỗi {path.name}: {e}")
        return []
    if not rows:
        return []

    out: list[dict] = []
    main_label: str | None = None
    main_source: str | None = None
    traffic_source: str | None = None
    headers: list[str] | None = None

    def norm_main(v: Any) -> tuple[str | None, str | None]:
        txt = str(v or "").strip()
        if txt in SHOPEE_TRAFFIC_MAIN:
            return txt, SHOPEE_TRAFFIC_MAIN[txt]
        return None, None

    for row in rows:
        if not row:
            continue
        vals = list(row)
        first = str(vals[0] or "").strip() if vals else ""
        nonempty = [x for x in vals if x not in (None, "")]

        # Heading of one of the four main sales sources.
        ml, ms = norm_main(first)
        if ml and len(nonempty) == 1:
            main_label, main_source = ml, ms
            traffic_source = None
            headers = None
            continue

        # Header under every main source block.
        if first.lower() == "nguồn lưu lượng":
            headers = unique_headers(vals)
            continue

        if not main_source or not headers:
            continue

        d = parse_date_any(first)
        if d:
            # A date always belongs to the most recent aggregate traffic-source row.
            if not traffic_source:
                continue
            # Chỉ giữ đúng các nhánh organic/affiliate thuộc nguồn doanh số.
            # Một số Shop Stats đặt tiếp các block Dịch vụ hiển thị/Ads ngay sau Affiliate;
            # nếu không chặn, parser sẽ gán nhầm Ads vào Tiếp thị liên kết.
            allowed = {
                "Product Card": {"Thẻ sản phẩm","Tìm kiếm","Đề xuất","Cửa hàng","Đơn mua của tôi","Giỏ hàng","Khuyến mãi","Chat","Khác"},
                "Live": {"Live","Cửa hàng","Giỏ hàng","Đề xuất","Tìm kiếm","Đơn mua của tôi","Video","Thẻ Live","Trang chủ Shopee Live","Chat","Khác"},
                "Video": {"Video","Tìm kiếm","Đề xuất","Cửa hàng","Giỏ hàng","Đơn mua của tôi","Thẻ Video","Video nổi bật","Trang chủ Shopee Video","Chat","Hồ sơ người tạo","Khác"},
                "Affiliate": {"Tiếp thị liên kết","Affiliate Video","Affiliate Live","Khác"},
            }
            if traffic_source not in allowed.get(main_source, set()):
                continue
            rec = row_to_dict(headers, vals)
            out.append({
                "platform": "Shopee",
                "date": d.isoformat(),
                "main_source": main_source,
                "main_label": main_label,
                "traffic_source": traffic_source,
                "gmv": safe_float(rec.get("Doanh số (VND)")),
                "reach": safe_float(
                    rec.get("Lượt hiển thị sản phẩm")
                    or rec.get("Lượt xem Livestream")
                    or rec.get("Lượt xem Video")
                    or rec.get("Lượt xem nội dung")
                ),
                "clicks": safe_float(rec.get("Lượt nhấp vào sản phẩm")),
                "orders": safe_float(rec.get("Tổng số đơn hàng")),
                "products": safe_float(rec.get("Sản phẩm")),
                "buyers": safe_float(rec.get("Người mua")) if rec.get("Người mua") not in (None, "") else None,
                "unique_reach": safe_float(
                    rec.get("Lượt hiển thị sản phẩm duy nhất")
                    or rec.get("Lượt xem Livestream duy nhất")
                    or rec.get("Lượt xem Video duy nhất")
                    or rec.get("Lượt xem nội dung duy nhất")
                ),
                "unique_clicks": safe_float(rec.get("Lượt nhấp sản phẩm duy nhất")),
                "source_file": path.name,
                "_mtime": path.stat().st_mtime,
            })
            continue

        # Aggregate row for a traffic source, followed by its daily rows.
        # Includes the total row (traffic_source == main label).
        if first and first.lower() not in {"nguồn lưu lượng", "ngày"}:
            traffic_source = first

    return out


SHOPEE_SOURCE_FILES = {
    "producttraffic_Product_Card": "Thẻ sản phẩm",
    "producttraffic_Seller_Live": "Phát trực tiếp",
    "producttraffic_Seller_Video": "Video",
    "producttraffic_Shopee_Affiliate": "Tiếp thị liên kết",
}


def parse_shopee_source(path: Path, source: str, warnings: list[str]) -> dict | None:
    try:
        _, rows = xlsx_read_sheet(path, lambda n, i, alln: "đơn đã xác nhận" in n.lower() and "lưu lượng" in n.lower())
    except Exception as e:
        warnings.append(f"Shopee {source} lỗi {path.name}: {e}")
        return None
    if not rows:
        return None
    hi = find_header_row(rows, ["mã sản phẩm", "doanh số"])
    if hi is None:
        warnings.append(f"Không thấy header {source}: {path.name}")
        return None
    headers = unique_headers(rows[hi])
    ps, pe = period_from_filename(path.name)
    if not ps:
        warnings.append(f"Không đọc được kỳ từ tên file {path.name}")
        return None
    products = []
    for row in rows[hi+1:]:
        if not row:
            continue
        rec = row_to_dict(headers, row)
        pid = str(rec.get("Mã sản phẩm") or "").strip()
        name = str(rec.get("Sản phẩm") or "").strip()
        if not pid or not name:
            continue
        brand, cat = classify_product(pid, name, "Shopee")
        gmv = safe_float(rec.get("Doanh số (VND)"))
        products.append({
            "platform": "Shopee", "source": source,
            "period_start": iso(ps), "period_end": iso(pe),
            "product_id": pid, "product_name": name, "brand": brand, "category": cat,
            "gmv": gmv,
            "orders": safe_float(rec.get("Tổng số đơn hàng")),
            "units": safe_float(rec.get("Sản phẩm_1")),
            "impressions": safe_float(rec.get("Lượt hiển thị sản phẩm")),
            "clicks": safe_float(rec.get("Lượt nhấp vào sản phẩm")),
            "ctr": safe_pct(rec.get("CTR")),
            "cvr": safe_pct(rec.get("Tỷ lệ chuyển đổi đơn hàng")),
            "aov": safe_float(rec.get("Doanh số trên mỗi đơn hàng")),
            "buyers": safe_float(rec.get("Người mua")),
            "source_file": path.name,
        })
    return {
        "platform": "Shopee", "source": source,
        "period_start": iso(ps), "period_end": iso(pe),
        "gmv": sum(x["gmv"] for x in products),
        "orders": sum(x["orders"] for x in products),
        "units": sum(x["units"] for x in products),
        "products": products, "source_file": path.name, "_mtime": path.stat().st_mtime,
    }


def _contribution_sheet_selector(prefix: str) -> Callable[[str, int, list[str]], bool]:
    def sel(n: str, i: int, names: list[str]) -> bool:
        contrib = [x for x in names if prefix.lower() in x.lower() and "contribution" in x.lower()]
        if len(contrib) >= 2:
            return n == contrib[1]  # placed, confirmed, paid -> confirmed = 2nd
        return False
    return sel


def parse_shopee_contribution(path: Path, kind: str, warnings: list[str]) -> dict | None:
    prefix = {"live":"Session", "video":"Video", "affiliate":"Affiliate"}[kind]
    try:
        _, rows = xlsx_read_sheet(path, _contribution_sheet_selector(prefix))
    except Exception as e:
        warnings.append(f"Contribution {kind} lỗi {path.name}: {e}")
        return None
    hi = find_header_row(rows, ["doanh số"])
    if hi is None:
        return None
    headers = unique_headers(rows[hi])
    ps, pe = period_from_filename(path.name)
    file_channel = None
    fname_lower = path.name.lower()
    if kind == "affiliate":
        if "affiliate_video" in fname_lower or "video_affiliate" in fname_lower:
            file_channel = "Video"
        elif "affiliate_live" in fname_lower or "live_affiliate" in fname_lower:
            file_channel = "Live"
    output_kind = ("affiliate_video" if file_channel=="Video" else "affiliate_live" if file_channel=="Live" else kind)
    items = []
    for row in rows[hi+1:]:
        if not row:
            continue
        rec = row_to_dict(headers, row)
        gmv = safe_float(rec.get("Doanh số (VND)"))
        if kind == "live":
            item_id = str(rec.get("Mã Phiên Chat") or "")
            title = str(rec.get("Session Title") or item_id)
            orders = safe_float(rec.get("psd_label_orders"))
            units = safe_float(rec.get("Sản phẩm"))
            creator = "Shopee Live"
        elif kind == "video":
            item_id = str(rec.get("psd_label_video_id") or "")
            title = str(rec.get("Video") or item_id)
            orders = safe_float(rec.get("psd_label_orders"))
            units = safe_float(rec.get("Sản phẩm"))
            creator = "Shopee Video"
        else:
            item_id = str(rec.get("Affiliate Username") or "")
            title = item_id
            orders = safe_float(rec.get("psd_label_orders"))
            units = safe_float(rec.get("Sản phẩm"))
            creator = item_id
        affiliate_channel = file_channel
        if kind == "affiliate":
            # Some Shopee exports may expose a channel/content-type column; keep it when present.
            raw_channel = " ".join(str(rec.get(k) or "") for k in (
                "Loại nội dung", "Nguồn", "Kênh", "Content Type", "Affiliate Type", "Loại tiếp thị", "Nguồn nội dung"
            )).lower()
            fname = path.name.lower()
            if "video" in raw_channel or "affiliate_video" in fname or "video_affiliate" in fname:
                affiliate_channel = "Video"
            elif "live" in raw_channel or "affiliate_live" in fname or "live_affiliate" in fname:
                affiliate_channel = "Live"
        if not item_id and not title:
            continue
        items.append({
            "platform":"Shopee", "kind":output_kind,
            "period_start":iso(ps), "period_end":iso(pe),
            "item_id":item_id, "title":title, "creator":creator,
            "gmv":gmv, "orders":orders, "units":units,
            "views":safe_float(rec.get("Lượt xem Video") or rec.get("Lượt xem Livestream") or rec.get("Lượt xem nội dung")),
            "clicks":safe_float(rec.get("Lượt nhấp vào sản phẩm")),
            "affiliate_channel": affiliate_channel if kind == "affiliate" else None,
            "source_file":path.name,
        })
    return {"platform":"Shopee","kind":output_kind,"period_start":iso(ps),"period_end":iso(pe),"items":items,"_mtime":path.stat().st_mtime,"source_file":path.name}


def parse_shopee_finance(path: Path, warnings: list[str]) -> dict | None:
    try:
        _, rows = xlsx_read_sheet(path, "Summary")
    except Exception as e:
        warnings.append(f"Shopee Finance lỗi {path.name}: {e}")
        return None
    ps = pe = None
    metrics: dict[str,float] = {}
    label_map = {
        "1. Tổng doanh thu":"revenue", "2. Tổng chi phí":"cost", "3. Tổng số tiền":"payout",
        "Tổng vận chuyển":"shipping", "Phí hoa hồng Tiếp thị liên kết":"affiliate_fee",
        "Phí cố định":"fixed_fee", "Phí Dịch Vụ":"service_fee", "Phí xử lý giao dịch":"transaction_fee",
        "Phí dịch vụ hiển thị NTTD (từ doanh thu đơn hàng)":"display_fee",
    }
    for r in rows:
        vals = [str(x).strip() if x not in (None,"") else "" for x in r]
        if vals and vals[0] == "Từ" and len(vals)>1:
            ps = parse_date_any(vals[1])
        if vals and vals[0] == "Đến" and len(vals)>1:
            pe = parse_date_any(vals[1])
        for lab,key in label_map.items():
            if lab in vals:
                metrics[key] = last_numeric_in_row(r)
    if not ps:
        ps, pe = period_from_filename(path.name)
    if not ps or not pe:
        warnings.append(f"Shopee Finance: không xác định được kỳ của {path.name}")
        return None
    cost = abs(metrics.get("cost",0))
    return {
        "platform":"Shopee","period_start":iso(ps),"period_end":iso(pe),
        "revenue":metrics.get("revenue",0),"cost":cost,"adjustment":0,
        "payout":metrics.get("payout",0),"shipping":metrics.get("shipping",0),
        "fixed_fee":abs(metrics.get("fixed_fee",0)),"service_fee":abs(metrics.get("service_fee",0)),
        "transaction_fee":abs(metrics.get("transaction_fee",0)),"affiliate_fee":abs(metrics.get("affiliate_fee",0)),
        "display_fee":abs(metrics.get("display_fee",0)),
        "source_file":path.name,"_mtime":path.stat().st_mtime,
    }


def read_csv_report(path: Path) -> tuple[tuple[date|None,date|None], list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    period=(None,None)
    for line in lines[:15]:
        if line.startswith("Khoảng thời gian,"):
            period=parse_period_text(line.split(",",1)[1])
            break
    hi=None
    for i,line in enumerate(lines):
        if line.startswith("Thứ tự,"):
            hi=i;break
    if hi is None:
        return period, [], []
    rows=list(csv.reader(lines[hi:]))
    return period, rows[0], rows[1:]


def parse_shopee_ads_file(path: Path, warnings: list[str]) -> dict | None:
    try:
        (ps,pe), headers, rows = read_csv_report(path)
        raw_head = "\n".join(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:8]).lower()
    except Exception as e:
        warnings.append(f"Shopee Ads lỗi {path.name}: {e}")
        return None
    if not headers:
        return None
    idx={h:i for i,h in enumerate(headers)}
    name=path.name.lower()
    subtype="Khác"
    headline=False
    chosen=rows

    # Ưu tiên nhận diện bằng nội dung report, không phụ thuộc tên file.
    # Cách này vẫn chạy đúng nếu file ZIP làm tên tiếng Việt bị mã hóa #Uxxxx.
    if "tự động chọn sản phẩm" in raw_head or "tự+động+chọn" in name or "auto" in name:
        subtype="Auto Product"
        # Report có dòng cha tổng + các dòng sản phẩm con. Chỉ lấy dòng cha để tránh nhân đôi.
        if "Mã sản phẩm" in idx:
            chosen=[r for r in rows if len(r)>idx["Mã sản phẩm"] and r[idx["Mã sản phẩm"]]=="-"][:1]
    elif "chiến dịch nhóm" in raw_head or "tất+cả+chiến+dịch+nhóm" in name or "chiến+dịch+nhóm" in name:
        subtype="Campaign Group"
        # Chỉ cộng dòng campaign cha; các dòng sản phẩm con đã nằm trong campaign cha.
        if "Mã sản phẩm" in idx:
            chosen=[r for r in rows if len(r)>idx["Mã sản phẩm"] and r[idx["Mã sản phẩm"]]=="-"]
    elif "livestream" in raw_head or "livestream" in name:
        subtype="Live Display"
    elif "tìm kiếm từ khóa ngành hàng" in raw_head or "shop+-ads-overall" in name or "shop+" in name:
        subtype="Shop Ads"
    elif ("cấp độ" in raw_head and "từ khóa" in raw_head and "vị trí" in raw_head) or "keyword" in name:
        # Dùng khi user có file headline/overview chính thức của Ads.
        subtype="Campaign Overview"
        headline=True

    def col(row: list[str], *keys: str) -> str:
        for key in keys:
            i=idx.get(key)
            if i is not None and i < len(row):
                return row[i]
        return ""

    cost=sum(safe_float_dot(col(r,"Chi phí")) for r in chosen)
    gmv=sum(safe_float_dot(col(r,"Doanh số")) for r in chosen)
    orders=sum(safe_float_dot(col(r,"Lượt chuyển đổi","Số đơn hàng")) for r in chosen)
    imps=sum(safe_float_dot(col(r,"Số lượt xem","Lượt xem")) for r in chosen)
    clicks=sum(safe_float_dot(col(r,"Số lượt click","Lượt click")) for r in chosen)
    return {
        "platform":"Shopee","subtype":subtype,"headline":headline,
        "period_start":iso(ps),"period_end":iso(pe),"cost":cost,"gmv":gmv,"orders":orders,
        "impressions":imps,"clicks":clicks,"source_file":path.name,"_mtime":path.stat().st_mtime,
    }


# -------------------------
# PARSE TIKTOK
# -------------------------
def parse_tiktok_overview(path: Path, warnings: list[str]) -> tuple[list[dict], dict|None]:
    try:
        _, rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Overview lỗi {path.name}: {e}")
        return [],None
    if not rows:
        return [],None
    ps,pe=parse_period_text(rows[0][0] if rows[0] else "")
    hi=find_header_row(rows,["gmv","đơn hàng","khách hàng"])
    if hi is None or hi+1>=len(rows):
        return [],None
    headers=unique_headers(rows[hi])
    total=row_to_dict(headers,rows[hi+1])

    def make(rec:dict,d:date,unique_ok:bool)->dict:
        gmv=safe_float_dot(rec.get("GMV"))
        live_aff=safe_float_dot(rec.get("GMV nhờ buổi LIVE của nhà sáng tạo"))
        live_seller=safe_float_dot(rec.get("GMV nhờ buổi LIVE của tài khoản kết nối"))
        video_aff=safe_float_dot(rec.get("GMV đến từ video liên kết"))
        video_seller=safe_float_dot(rec.get("GMV nhờ video của tài khoản kết nối"))
        return {
            "platform":"TikTok","date":d.isoformat(),"gmv":gmv,
            "orders":safe_float_dot(rec.get("Đơn hàng")),"sku_orders":safe_float_dot(rec.get("Đơn hàng SKU")),
            "customers":safe_float_dot(rec.get("Khách hàng")) if unique_ok else None,
            "units":safe_float_dot(rec.get("Số món bán ra")),"refund":safe_float_dot(rec.get("Hoàn tiền")),
            "cancel_gmv":None,"revenue":safe_float_dot(rec.get("Tổng doanh thu")),"page_views":safe_float_dot(rec.get("Lượt xem trang")),
            "visitors":safe_float_dot(rec.get("Khách truy cập")),"cvr":safe_float_dot(rec.get("Tỷ lệ chuyển đổi")),
            "product_impressions":safe_float_dot(rec.get("Lượt hiển thị sản phẩm")),"product_clicks":safe_float_dot(rec.get("Lượt nhấp vào sản phẩm")),
            "aov":safe_float_dot(rec.get("AOV")),"live_aff":live_aff,"live_seller":live_seller,"video_aff":video_aff,"video_seller":video_seller,
            "cancel_orders":None,"refund_orders":None,"source_file":path.name,"_mtime":path.stat().st_mtime,
        }

    daily=[]
    # Tìm header Daily có cột đầu Ngày
    daily_hi=None
    for i in range(hi+2,len(rows)):
        if rows[i] and str(rows[i][0] or "").strip().lower()=="ngày":
            daily_hi=i;break
    if daily_hi is not None:
        dh=unique_headers(rows[daily_hi])
        for r in rows[daily_hi+1:]:
            if not r or not r[0]:continue
            d=parse_date_any(r[0])
            if not d:continue
            rec=row_to_dict(dh,r)
            daily.append(make(rec,d,True if ps==pe else False))
    elif ps and ps==pe:
        daily.append(make(total,ps,True))
    if ps and pe and ps==pe and daily:
        # đảm bảo unique / refund lấy total row vì hourly có thể không có refund
        daily=[make(total,ps,True)]

    summary={
        "platform":"TikTok","period_start":iso(ps),"period_end":iso(pe),"gmv":safe_float_dot(total.get("GMV")),
        "orders":safe_float_dot(total.get("Đơn hàng")),"sku_orders":safe_float_dot(total.get("Đơn hàng SKU")),
        "customers":safe_float_dot(total.get("Khách hàng")),"cvr":safe_float_dot(total.get("Tỷ lệ chuyển đổi")),"refund":safe_float_dot(total.get("Hoàn tiền")),
        "cancel_gmv":None,"cancel_orders":None,"refund_orders":None,"source_file":path.name,"_mtime":path.stat().st_mtime,
    } if ps else None
    return daily,summary


def report_period_from_first_rows(rows:list[list[Any]], fallback_name:str)->tuple[date|None,date|None]:
    for r in rows[:5]:
        if r and r[0]:
            ps,pe=parse_period_text(r[0])
            if ps:return ps,pe
    return period_from_filename(fallback_name)


def parse_tiktok_productcard(path:Path,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok ProductCard lỗi {path.name}: {e}");return None
    ps,pe=report_period_from_first_rows(rows,path.name)
    f_ps,f_pe=period_from_filename(path.name)
    if ps and f_ps and ps!=f_ps:
        warnings.append(f"TikTok ProductCard {path.name}: tên file gợi ý {f_ps.isoformat()} nhưng nội dung là {ps.isoformat()}; hệ thống dùng ngày trong nội dung.")
    hi=find_header_row(rows,["id sản phẩm","gmv"])
    if hi is None:return None
    h=unique_headers(rows[hi]); products=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);pid=str(rec.get("ID sản phẩm") or "").strip();nm=str(rec.get("Tên sản phẩm") or "").strip()
        if not pid or not nm:continue
        brand,cat=classify_product(pid,nm,"TikTok")
        products.append({
            "platform":"TikTok","source":"Thẻ sản phẩm","period_start":iso(ps),"period_end":iso(pe),
            "product_id":pid,"product_name":nm,"brand":brand,"category":cat,
            "gmv":safe_float_dot(rec.get("GMV (₫)")),"orders":safe_float_dot(rec.get("Đơn hàng SKU")),"units":None,
            "impressions":safe_float_dot(rec.get("Lượt xem")),"clicks":safe_float_dot(rec.get("Lượt nhấp")),
            "ctr":safe_pct(rec.get("Tỷ lệ từ xem đến nhấp")),"cvr":safe_pct(rec.get("Tỷ lệ từ xem đến thanh toán")),
            "aov":None,"buyers":safe_float_dot(rec.get("Khách hàng")),"source_file":path.name,
        })
    return {"platform":"TikTok","source":"Thẻ sản phẩm","period_start":iso(ps),"period_end":iso(pe),"gmv":sum(x["gmv"] for x in products),"products":products,"source_file":path.name,"_mtime":path.stat().st_mtime}


def parse_tiktok_live(path:Path,affiliate:bool,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Live lỗi {path.name}: {e}");return None
    ps,pe=report_period_from_first_rows(rows,path.name)
    hi=find_header_row(rows,["nhà sáng tạo","gmv đến từ buổi live"])
    if hi is None:return None
    h=unique_headers(rows[hi]);items=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);creator=str(rec.get("Biệt danh") or rec.get("Nhà sáng tạo") or "").strip()
        if not creator:continue
        gmv=safe_float_dot(rec.get("GMV đến từ buổi LIVE (₫)"))
        items.append({
            "platform":"TikTok","kind":"affiliate_live" if affiliate else "live",
            "period_start":iso(ps),"period_end":iso(pe),"item_id":str(rec.get("ID nhà sáng tạo") or ""),
            "title":str(rec.get("Nhà sáng tạo") or creator),"creator":creator,"gmv":gmv,
            "orders":safe_float_dot(rec.get("Đơn hàng đã tạo")),"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào buổi LIVE")),
            "views":safe_float_dot(rec.get("Lượt xem")),"clicks":safe_float_dot(rec.get("Lượt nhấp Sản phẩm")),"source_file":path.name,
        })
    return {"platform":"TikTok","kind":"affiliate_live" if affiliate else "live","period_start":iso(ps),"period_end":iso(pe),"items":items,"_mtime":path.stat().st_mtime,"source_file":path.name}


def parse_tiktok_video(path:Path,affiliate:bool,warnings:list[str])->tuple[dict|None,list[dict]]:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Video lỗi {path.name}: {e}");return None,[]
    ps,pe=report_period_from_first_rows(rows,path.name)
    hi=find_header_row(rows,["id video","gmv đến từ video"])
    if hi is None:return None,[]
    h=unique_headers(rows[hi]);items=[];product_facts=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);vid=str(rec.get("ID video") or "").strip();creator=str(rec.get("Tên nhà sáng tạo") or "").strip()
        if not vid and not creator:continue
        gmv=safe_float_dot(rec.get("GMV đến từ video (₫)"));orders=safe_float_dot(rec.get("Đơn hàng SKU đã ghi nhận"))
        if gmv<=0 and orders<=0:continue
        products=parse_tiktok_products(rec.get("Sản phẩm"))
        cats=[];brands=[]
        for pid,nm in products:
            br,ca=classify_product(pid,nm,"TikTok");cats.append(ca);brands.append(br)
        cat="CHƯA GÁN";brand="CHƯA GÁN"
        if cats:
            uniq={x for x in cats if x!="CHƯA GÁN"}
            cat=next(iter(uniq)) if len(uniq)==1 else ("Đa ngành / chưa phân bổ" if len(uniq)>1 else "CHƯA GÁN")
            ub={x for x in brands if x!="CHƯA GÁN"}
            brand=next(iter(ub)) if len(ub)==1 else "CHƯA GÁN"
        items.append({
            "platform":"TikTok","kind":"affiliate_video" if affiliate else "video",
            "period_start":iso(ps),"period_end":iso(pe),"item_id":vid,"title":str(rec.get("Thông tin video") or vid),"creator":creator,
            "gmv":gmv,"orders":orders,"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào video")),
            "views":safe_float_dot(rec.get("VV")),"clicks":safe_float_dot(rec.get("Lượt nhấp sản phẩm")),"source_file":path.name,
        })
        source="Tiếp thị liên kết" if affiliate else "Video"
        if len(products)==1:
            pid,nm=products[0];br,ca=classify_product(pid,nm,"TikTok")
            pname=nm;pid_out=pid
        else:
            pname="Đa sản phẩm";pid_out=vid
            br,ca=brand,cat
        product_facts.append({
            "platform":"TikTok","source":source,"period_start":iso(ps),"period_end":iso(pe),
            "product_id":pid_out,"product_name":pname,"brand":br,"category":ca,
            "gmv":gmv,"orders":orders,"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào video")),
            "impressions":safe_float_dot(rec.get("Lượt hiển thị sản phẩm")),"clicks":safe_float_dot(rec.get("Lượt nhấp sản phẩm")),
            "ctr":safe_pct(rec.get("Tỷ lệ nhấp (Video)")),"cvr":safe_pct(rec.get("CTOR (đơn hàng SKU)")),"aov":None,"buyers":safe_float_dot(rec.get("Số khách hàng độc nhất")),"source_file":path.name,
        })
    return {"platform":"TikTok","kind":"affiliate_video" if affiliate else "video","period_start":iso(ps),"period_end":iso(pe),"items":items,"_mtime":path.stat().st_mtime,"source_file":path.name},product_facts


def parse_tiktok_ads(path:Path,warnings:list[str])->list[dict]:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Ads lỗi {path.name}: {e}");return []
    ps,pe=period_from_filename(path.name)
    hi=find_header_row(rows,["tên chiến dịch","chi phí"])
    if hi is None:
        warnings.append(f"TikTok Ads: không tìm thấy cột tên chiến dịch/chi phí: {path.name}"); return []
    if not ps or not pe:
        warnings.append(f"TikTok Ads: không xác định được kỳ trong tên file: {path.name}"); return []
    h=unique_headers(rows[hi])
    daily_mode="Theo ngày" in h
    agg:dict[tuple,dict]= {}
    seen=set()
    is_live="livestream" in path.name.lower() or path.name.lower().startswith("live campaign data")
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r)
        camp=str(rec.get("Tên chiến dịch") or rec.get("Tên phiên LIVE") or "").strip()
        if not camp:continue
        day=parse_date_any(rec.get("Theo ngày")) if daily_mode else None
        if daily_mode and (not day or not ps<=day<=pe):
            warnings.append(f"TikTok Ads: ngày trống/sai/ngoài kỳ tại {path.name}; bỏ toàn bộ file để tránh thiếu số.")
            return []
        campaign_id=str(rec.get("ID chiến dịch") or camp)
        if daily_mode:
            identity=(campaign_id,iso(day))
            if identity in seen:
                warnings.append(f"TikTok Ads: trùng chiến dịch/ngày trong {path.name}; bỏ file để tránh cộng trùng.")
                return []
            seen.add(identity)
        start=end=day
        if not daily_mode: start,end=ps,pe
        cost=safe_float_dot(rec.get("Chi phí"));gmv=safe_float_dot(rec.get("Doanh thu gộp"));orders=safe_float_dot(rec.get("Số lượng đơn hàng SKU"))
        pid=str(rec.get("ID sản phẩm") or "").strip();creative=str(rec.get("Loại nội dung sáng tạo") or ("Livestream" if is_live else "Khác"))
        creator=str(rec.get("Tài khoản TikTok") or "")
        br,ca=classify_product(pid,camp,"TikTok") if pid else ("CHƯA GÁN","CHƯA GÁN")
        key=(campaign_id,creative,br,ca,iso(start),iso(end))
        if key not in agg:
            agg[key]={"platform":"TikTok","period_start":iso(start),"period_end":iso(end),"campaign_id":campaign_id,"grain":"daily" if daily_mode else "period","subtype":"TikTok Live Ads" if is_live else "TikTok Product Ads","source_mtime":path.stat().st_mtime,"campaign":camp,"creative_type":creative,"brand":br,"category":ca,"cost":0.0,"gmv":0.0,"orders":0.0,"impressions":0.0,"clicks":0.0,"source_file":path.name,"_mtime":path.stat().st_mtime}
        a=agg[key];a["cost"]+=cost;a["gmv"]+=gmv;a["orders"]+=orders
        a["impressions"]+=safe_float_dot(rec.get("Số lượt hiển thị quảng cáo sản phẩm") or rec.get("Số lượt xem phiên LIVE"))
        a["clicks"]+=safe_float_dot(rec.get("Số lượt nhấp vào quảng cáo sản phẩm"))
    return list(agg.values())


def inspect_tiktok_finance_detail(path, summary, warnings):
    """Only expose daily totals when dated detail reconciles to the report."""
    summary["daily_rows"] = []
    summary["source_mtime"] = path.stat().st_mtime
    try:
        _, rows = xlsx_read_sheet(path, "Chi tiết đơn hàng")
        headers = [str(x or "").strip() for x in rows[0]]
        labels = {"date": "Thời gian quyết toán đơn hàng", "revenue": "Tổng doanh thu",
                  "cost": "Tổng phí", "payout": "Tổng số tiền quyết toán"}
        cols = {k: headers.index(v) for k, v in labels.items()}
        totals = dict(revenue=0., cost=0., payout=0.)
        by_date = {}; count = 0; valid = True
        start, end = parse_date_any(summary["period_start"]), parse_date_any(summary["period_end"])
        for row in rows[1:]:
            if not any(x not in (None, "") for x in row):
                continue
            count += 1
            dt = parse_date_any(row[cols["date"]] if cols["date"] < len(row) else None)
            if not dt or not start <= dt <= end:
                valid = False
                continue
            values = {}
            for key in ("revenue", "cost", "payout"):
                cell = row[cols[key]] if cols[key] < len(row) else None
                try:
                    values[key] = float(str(cell).strip())
                    if not math.isfinite(values[key]): valid = False
                except (ValueError, TypeError):
                    valid = False
                    values[key] = 0.
            day = by_date.setdefault(iso(dt), dict(revenue=0., cost=0., payout=0.))
            for key, val in values.items():
                totals[key] += val
                day[key] += val
        summary["detail_count"] = count
        summary["detail_payout"] = totals["payout"]
        reconciled = valid and count > 0 and totals["cost"] <= 0 and abs(abs(totals["payout"]-totals["revenue"]-totals["cost"])-summary["adjustment"]) <= 1 and all(abs((abs(totals[k]) if k == "cost" else totals[k]) - summary[k]) <= 1 for k in totals)
        summary["detail_status"] = "reconciled" if reconciled else "incomplete"
        if not reconciled:
            summary["detail_note"] = f"Chi tiết có {count} giao dịch, tổng quyết toán {totals['payout']:,.0f}đ; tổng báo cáo {summary['payout']:,.0f}đ. Chưa đối soát đủ để tách ngày."
            warnings.append(f"TikTok Finance {path.name}: " + summary["detail_note"])
            return summary
        # Reconciled report covers every date in its declared range, including zero-activity days.
        dt = start
        while dt <= end:
            v = by_date.get(iso(dt), dict(revenue=0., cost=0., payout=0.))
            summary["daily_rows"].append({"platform": "TikTok", "period_start": iso(dt), "period_end": iso(dt),
                "revenue": v["revenue"], "cost": -v["cost"],
                "adjustment": v["payout"]-v["revenue"]-v["cost"], "payout": v["payout"],
                "source_file": path.name, "note": "Theo ngày quyết toán; chi tiết đã khớp tổng kỳ"})
            dt += timedelta(days=1)
        summary["detail_note"] = "Chi tiết theo ngày quyết toán đã khớp doanh thu, phí và tiền quyết toán tổng kỳ. Điều chỉnh theo ngày giữ dấu."
    except Exception as exc:
        summary["detail_status"] = "unavailable"
        summary["detail_note"] = "Chưa đọc được chi tiết theo ngày quyết toán: " + str(exc)
        warnings.append(f"TikTok Finance {path.name}: " + summary["detail_note"])
    return summary


def parse_tiktok_finance(path:Path,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,"Báo cáo")
    except Exception as e:
        warnings.append(f"TikTok Finance lỗi {path.name}: {e}");return None
    ps=pe=None;vals={}
    wanted={"Tổng số tiền quyết toán":"payout","Tổng doanh thu":"revenue","Tổng phí":"cost","Điều chỉnh":"adjustment",
            "Phí giao dịch":"transaction_fee","Phí hoa hồng của TikTok Shop":"commission_fee","Phí vận chuyển của người bán":"shipping_fee",
            "Hoa hồng liên kết":"affiliate_fee","Hoa hồng liên kết Quảng cáo cửa hàng":"affiliate_ads_fee","Phí dịch vụ Voucher Xtra":"voucher_fee","Phí xử lý đơn hàng":"processing_fee",
            "GMV thanh toán cho Quảng cáo TikTok":"ads_adjustment"}
    for r in rows:
        cells=[str(x).strip() if x not in (None,"") else "" for x in r]
        if "Khoảng thời gian" in cells:
            txt=next((x for x in cells if "20" in x and "/" in x),"");ps,pe=parse_period_text(txt)
        for lab,key in wanted.items():
            if lab in cells:
                vals[key]=last_numeric_in_row(r)
    if not ps:ps,pe=period_from_filename(path.name)
    if not ps or not pe:
        warnings.append(f"TikTok Finance: không xác định được kỳ của {path.name}")
        return None
    result = {"platform":"TikTok","period_start":iso(ps),"period_end":iso(pe),"revenue":vals.get("revenue",0),"cost":abs(vals.get("cost",0)),"adjustment":abs(vals.get("adjustment",0)),"payout":vals.get("payout",0),"transaction_fee":abs(vals.get("transaction_fee",0)),"commission_fee":abs(vals.get("commission_fee",0)),"shipping_fee":abs(vals.get("shipping_fee",0)),"affiliate_fee":abs(vals.get("affiliate_fee",0)),"affiliate_ads_fee":abs(vals.get("affiliate_ads_fee",0)),"voucher_fee":abs(vals.get("voucher_fee",0)),"processing_fee":abs(vals.get("processing_fee",0)),"ads_adjustment":abs(vals.get("ads_adjustment",0)),"source_file":path.name,"_mtime":path.stat().st_mtime}
    return inspect_tiktok_finance_detail(path, result, warnings)


# -------------------------
# ETL TOÀN BỘ
# -------------------------
def collect_data(input_root:Path)->dict:
    warnings=[]
    daily=[];overview_summaries=[];source_periods=[];product_facts=[];content_periods=[];traffic_daily=[];ads=[];finance=[]

    # Shopee overview + nguồn lưu lượng chi tiết. Hỗ trợ cả tên Shop Stats và Báo Cáo Tổng Quan SHOPEE.
    shopee_overview_files = []
    seen_overview_paths = set()
    for pattern in ("*shopee-shop-stats*.xlsx", "Báo Cáo Tổng Quan SHOPEE*.xlsx", "Bao Cao Tong Quan SHOPEE*.xlsx"):
        for p in input_root.rglob(pattern):
            rp=str(p.resolve())
            if rp not in seen_overview_paths:
                seen_overview_paths.add(rp); shopee_overview_files.append(p)
    for p in shopee_overview_files:
        d,s=parse_shopee_overview(p,warnings);daily.extend(d)
        if s:overview_summaries.append(s)
        traffic_daily.extend(parse_shopee_traffic_daily(p,warnings))

    # Shopee sources + contribution
    for p in input_root.rglob("producttraffic_*.xlsx"):
        matched=None
        for token,src in SHOPEE_SOURCE_FILES.items():
            if token in p.name:
                matched=src;break
        if matched:
            lname=p.name.lower()
            channel_specific_aff = matched=="Tiếp thị liên kết" and any(t in lname for t in ("affiliate_video","video_affiliate","affiliate_live","live_affiliate"))
            if not channel_specific_aff:
                sp=parse_shopee_source(p,matched,warnings)
                if sp:source_periods.append(sp);product_facts.extend(sp["products"])
        if "Seller_Live" in p.name:
            c=parse_shopee_contribution(p,"live",warnings)
            if c:content_periods.append(c)
        elif "Seller_Video" in p.name:
            c=parse_shopee_contribution(p,"video",warnings)
            if c:content_periods.append(c)
        elif "Shopee_Affiliate" in p.name:
            c=parse_shopee_contribution(p,"affiliate",warnings)
            if c:content_periods.append(c)

    # Shopee finance
    for p in input_root.rglob("Income*.xlsx"):
        # tránh TikTok income_...
        if "SHOPEE" in str(p).upper() or p.name.startswith("Income"):
            f=parse_shopee_finance(p,warnings)
            if f:finance.append(f)

    # Shopee Ads CSV
    for p in input_root.rglob("*.csv"):
        if "SHOPEE" in str(p).upper():
            a=parse_shopee_ads_file(p,warnings)
            if a:ads.append(a)

    # TikTok overview
    for p in input_root.rglob("Shop Analytics_Key metrics*.xlsx"):
        d,s=parse_tiktok_overview(p,warnings);daily.extend(d)
        if s:overview_summaries.append(s)

    # TikTok Product Card
    for p in input_root.rglob("Products Card List*.xlsx"):
        sp=parse_tiktok_productcard(p,warnings)
        if sp:source_periods.append(sp);product_facts.extend(sp["products"])

    # TikTok Live current + Affiliate Live
    # Nhận diện bằng cả tên file và folder, để hỗ trợ kiểu tên "Tiếp Thị Liên Kết".
    def is_affiliate_path(p: Path) -> bool:
        txt=(p.name+" "+str(p.parent)).lower()
        return ("affiliate" in txt) or ("tiếp thị" in txt) or ("tiep thi" in txt)

    for p in input_root.rglob("Live Analysis*.xlsx"):
        if "TIKTOK" not in str(p).upper():
            continue
        c=parse_tiktok_live(p,is_affiliate_path(p),warnings)
        if c:content_periods.append(c)

    # Tên "Live Affiliate Analysis..." không bắt đầu bằng "Live Analysis"
    for p in input_root.rglob("Live Affiliate Analysis*.xlsx"):
        if "TIKTOK" in str(p).upper():
            c=parse_tiktok_live(p,True,warnings)
            if c:content_periods.append(c)

    # TikTok Video current + Affiliate Video
    for p in input_root.rglob("Video Performance List*.xlsx"):
        if "TIKTOK" not in str(p).upper():
            continue
        aff=is_affiliate_path(p)
        c,pf=parse_tiktok_video(p,aff,warnings)
        if c:content_periods.append(c)
        product_facts.extend(pf)

    # Tên "Video Affiliate Performance..." không bắt đầu bằng "Video Performance List"
    for p in input_root.rglob("Video Affiliate Performance*.xlsx"):
        if "TIKTOK" in str(p).upper():
            c,pf=parse_tiktok_video(p,True,warnings)
            if c:content_periods.append(c)
            product_facts.extend(pf)

    # TikTok Ads
    for p in input_root.rglob("*.xlsx"):
        name=p.name.lower()
        if name.startswith(("product campaign data", "live campaign data")) or ("data for " in name and "campaigns" in name):
            ads.extend(parse_tiktok_ads(p,warnings))

    # TikTok Finance
    for p in input_root.rglob("income_*.xlsx"):
        f=parse_tiktok_finance(p,warnings)
        if f:finance.append(f)

    # Dedup daily by platform/date (newest wins)
    daily=dedup_by_period(daily,("platform","date"))
    overview_summaries=dedup_by_period(overview_summaries,("platform","period_start","period_end"))
    source_periods=dedup_by_period(source_periods,("platform","source","period_start","period_end"))
    content_periods=dedup_by_period(content_periods,("platform","kind","period_start","period_end"))
    finance=dedup_by_period(finance,("platform","period_start","period_end"))
    # Nguồn lưu lượng Shopee: mỗi ngày + nguồn chính + nguồn con chỉ giữ file mới nhất.
    traffic_best={}
    for r in traffic_daily:
        k=(r.get("date"),r.get("main_source"),r.get("traffic_source"))
        old=traffic_best.get(k)
        if old is None or r.get("_mtime",0)>=old.get("_mtime",0):
            traffic_best[k]=r
    traffic_daily=list(traffic_best.values())
    # Campaign-level reports take precedence over creative detail for the same family/period.
    # Never add both views together; newest whole file wins within each report type.
    snapshots={}
    for r in ads:
        if r.get("platform") != "TikTok": continue
        key=(_ads_family(r),r.get("period_start"),r.get("period_end"))
        name=r.get("source_file", "")
        rank=("campaign data" in name.lower(),r.get("_mtime",0),name)
        if key not in snapshots or rank>snapshots[key]: snapshots[key]=rank
    ads=[r for r in ads if r.get("platform")!="TikTok" or
         r.get("source_file")==snapshots[(_ads_family(r),r.get("period_start"),r.get("period_end"))][2]]

    # Lấy product facts đúng với source/content period còn sống để tránh snapshot cũ bị cộng lại.
    alive_source={(r["platform"],r["source"],r["period_start"],r["period_end"],r["source_file"]) for r in source_periods}
    alive_content={(r["platform"],r["kind"],r["period_start"],r["period_end"],r["source_file"]) for r in content_periods}
    kept=[]
    for x in product_facts:
        key_source=(x["platform"],x["source"],x["period_start"],x["period_end"],x["source_file"])
        if key_source in alive_source:
            kept.append(x);continue
        if x["platform"]=="TikTok" and x["source"]=="Video":
            if ("TikTok","video",x["period_start"],x["period_end"],x["source_file"]) in alive_content:
                kept.append(x)
        elif x["platform"]=="TikTok" and x["source"]=="Tiếp thị liên kết":
            if ("TikTok","affiliate_video",x["period_start"],x["period_end"],x["source_file"]) in alive_content:
                kept.append(x)
    product_facts=kept

    # Product catalog phục vụ Ads/category
    catalog={}
    for x in product_facts:
        pid=str(x.get("product_id") or "")
        if pid and x.get("product_name") not in {"Đa sản phẩm",""}:
            catalog[pid]={"name":x.get("product_name"),"brand":x.get("brand"),"category":x.get("category")}
    for a in ads:
        if a.get("platform")=="TikTok" and a.get("category")=="CHƯA GÁN":
            # Nếu campaign không đủ, giữ CHƯA GÁN. Aggregation không lưu PID nên không ép gán.
            pass

    # Remove internal mtime before JSON/CSV
    for coll in [daily,overview_summaries,source_periods,content_periods,traffic_daily,ads,finance]:
        for r in coll:r.pop("_mtime",None)

    # Sort
    daily.sort(key=lambda x:(x["date"],x["platform"]))
    traffic_daily.sort(key=lambda x:(x.get("date") or "",x.get("main_source") or "",x.get("traffic_source") or ""))
    product_facts.sort(key=lambda x:(x.get("period_start") or "",x.get("platform") or "",x.get("source") or "",-x.get("gmv",0)))
    return {"daily":daily,"overview_summaries":overview_summaries,"source_periods":source_periods,"product_facts":product_facts,"content_periods":content_periods,"traffic_daily":traffic_daily,"ads":ads,"finance":finance,"warnings":warnings}



# -------------------------
# KHO LỊCH SỬ BỀN VỮNG
# -------------------------
def _empty_store() -> dict:
    return {
        "daily": [], "overview_summaries": [], "source_periods": [],
        "product_facts": [], "content_periods": [], "traffic_daily": [], "ads": [],
        "finance": [], "warnings": []
    }


def load_history_store(path: Path) -> dict:
    if not path.exists():
        return _empty_store()
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("HistoryStore không phải JSON object")
        out = _empty_store()
        for k in out:
            if k == "warnings":
                continue
            v = obj.get(k, [])
            out[k] = v if isinstance(v, list) else []
        return out
    except Exception as e:
        raise RuntimeError(f"Không đọc được kho lịch sử {path}: {e}") from e


def save_history_store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: data.get(k, []) for k in _empty_store() if k != "warnings"}
    payload["_meta"] = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Kho lịch sử Diligo. Không xóa file này nếu muốn giữ dữ liệu đã import."
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _merge_simple(old: list[dict], new: list[dict], fields: tuple[str, ...]) -> list[dict]:
    m = {tuple(r.get(f) for f in fields): r for r in old}
    for r in new:
        m[tuple(r.get(f) for f in fields)] = r
    return list(m.values())


def _ads_family(r: dict) -> str:
    if r.get("platform") == "Shopee":
        return str(r.get("subtype") or "Shopee Ads")
    sf = str(r.get("source_file") or "").lower()
    return "TikTok Live Ads" if "livestream" in sf or sf.startswith("live campaign data") else "TikTok Product Ads"


def merge_history_store(history: dict, current: dict) -> dict:
    """Ghép lần import mới vào kho cũ. Kỳ trùng nhau: dữ liệu mới thay thế kỳ cũ."""
    out = _empty_store()
    out["daily"] = _merge_simple(history.get("daily", []), current.get("daily", []), ("platform", "date"))
    out["overview_summaries"] = _merge_simple(
        history.get("overview_summaries", []), current.get("overview_summaries", []),
        ("platform", "period_start", "period_end")
    )
    out["source_periods"] = _merge_simple(
        history.get("source_periods", []), current.get("source_periods", []),
        ("platform", "source", "period_start", "period_end")
    )
    out["content_periods"] = _merge_simple(
        history.get("content_periods", []), current.get("content_periods", []),
        ("platform", "kind", "period_start", "period_end")
    )
    out["traffic_daily"] = _merge_simple(
        history.get("traffic_daily", []), current.get("traffic_daily", []),
        ("platform", "date", "main_source", "traffic_source")
    )
    out["finance"] = _merge_simple(
        history.get("finance", []), current.get("finance", []),
        ("platform", "period_start", "period_end")
    )

    # Product facts: khi một kỳ nguồn được import lại, thay toàn bộ chi tiết sản phẩm của kỳ đó.
    touched = set()
    for r in current.get("source_periods", []):
        touched.add((r.get("platform"), r.get("source"), r.get("period_start"), r.get("period_end")))
    for r in current.get("content_periods", []):
        if r.get("platform") == "TikTok" and r.get("kind") in {"video", "affiliate_video"}:
            src = "Video" if r.get("kind") == "video" else "Tiếp thị liên kết"
            touched.add(("TikTok", src, r.get("period_start"), r.get("period_end")))
    for r in current.get("product_facts", []):
        touched.add((r.get("platform"), r.get("source"), r.get("period_start"), r.get("period_end")))

    old_pf = [r for r in history.get("product_facts", [])
              if (r.get("platform"), r.get("source"), r.get("period_start"), r.get("period_end")) not in touched]
    pf = old_pf + current.get("product_facts", [])
    out["product_facts"] = _merge_simple(
        [], pf,
        ("platform", "source", "period_start", "period_end", "product_id", "product_name", "source_file")
    )

    # Ads: thay theo đúng loại báo cáo + kỳ, tránh giữ campaign cũ khi tải lại kỳ đã sửa.
    touched_ads = {(_ads_family(r), r.get("platform"), r.get("period_start"), r.get("period_end"))
                   for r in current.get("ads", [])}
    old_ads = [r for r in history.get("ads", [])
               if (_ads_family(r), r.get("platform"), r.get("period_start"), r.get("period_end")) not in touched_ads]
    ads = old_ads + current.get("ads", [])
    out["ads"] = _merge_simple(
        [], ads,
        ("platform", "subtype", "headline", "campaign", "creative_type", "brand", "category", "period_start", "period_end", "source_file")
    )

    out["warnings"] = list(current.get("warnings", []))
    out["daily"].sort(key=lambda x: (x.get("date") or "", x.get("platform") or ""))
    out["traffic_daily"].sort(key=lambda x: (x.get("date") or "", x.get("main_source") or "", x.get("traffic_source") or ""))
    out["product_facts"].sort(key=lambda x: (x.get("period_start") or "", x.get("platform") or "", x.get("source") or "", -float(x.get("gmv") or 0)))
    return out


def preferred_report_period(current: dict, merged: dict) -> tuple[str, str] | None:
    """Mặc định mở kỳ mới nhất vừa import; nếu Data_Input trống thì dùng kỳ mới nhất trong kho."""
    def choose(d: dict):
        periods=[]
        for r in d.get("overview_summaries", []):
            a,b=r.get("period_start"),r.get("period_end") or r.get("period_start")
            if a and b: periods.append((a,b))
        if periods:
            latest_end=max(b for _,b in periods)
            same=[x for x in periods if x[1]==latest_end]
            # Hai sàn thường cùng kỳ; lấy start nhỏ nhất nếu có chênh nhẹ.
            return (min(a for a,_ in same), latest_end)
        dates=sorted({r.get("date") for r in d.get("daily", []) if r.get("date")})
        return (dates[-1], dates[-1]) if dates else None
    return choose(current) or choose(merged)

# -------------------------
# OUTPUT CSV
# -------------------------
def write_csv(path:Path,rows:list[dict],fields:list[str]|None=None)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None:
        fields=[]
        seen=set()
        for r in rows:
            for k in r:
                if k not in seen and not k.startswith("_"):
                    seen.add(k);fields.append(k)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rows)


def flatten_source_periods(periods:list[dict])->list[dict]:
    return [{k:v for k,v in r.items() if k!="products"} for r in periods]


def flatten_content(periods:list[dict])->list[dict]:
    out=[]
    for p in periods:
        for it in p.get("items",[]):out.append(it)
    return out


# -------------------------
# HTML DASHBOARD
# -------------------------
HTML_TEMPLATE = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diligo E-commerce Dashboard</title>
<style>
:root{--orange:#f05a28;--orange2:#fff0e9;--ink:#202124;--muted:#6b7280;--line:#e5e7eb;--bg:#f5f6f8;--green:#0d9f6e;--blue:#2563eb;--red:#dc2626}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Arial,Helvetica,sans-serif}.wrap{max-width:1440px;margin:auto;padding:20px}.top{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:14px;padding-top:12px;padding-bottom:12px}.brand{display:flex;align-items:center;gap:10px}.logo{width:36px;height:36px;border-radius:10px;background:var(--orange);color:#fff;display:grid;place-items:center;font-weight:900}.brand h1{font-size:17px;margin:0}.brand small{color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.filters input,.filters select,.filters button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 10px}.filters button{background:var(--orange);color:#fff;border-color:var(--orange);cursor:pointer;font-weight:700}.card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px rgba(0,0,0,.03)}.section{padding:18px;margin:14px 0}.sectionHead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}.sectionHead h2{font-size:16px;margin:0}.sectionHead small,.sub,.note,.foot{color:var(--muted);font-size:12px}.chip{border-radius:99px;padding:5px 9px;background:#eef2ff;font-size:11px;font-weight:700}.chip.ok{background:#e8f8f1;color:#087a53}.chip.warn{background:#fff3cd;color:#8a6200}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.kpi{padding:14px}.kpi .lab{font-size:12px;color:var(--muted)}.kpi .val{font-size:23px;font-weight:900;margin-top:4px}.kpi .sub{margin-top:3px}.sources{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.source{padding:13px;cursor:pointer}.source.active{border-color:var(--orange);background:#fffaf7}.source .shead{display:flex;justify-content:space-between;gap:8px}.source .sname{font-size:12px;color:var(--muted)}.source .sshare{font-size:12px;font-weight:800;color:var(--orange)}.source .sval{font-size:18px;font-weight:900;margin-top:5px}.bar{height:5px;background:#eee;border-radius:10px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--orange)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.panel{padding:14px}.metric{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px dashed #eee}.metric:last-child{border-bottom:0}.metric b{text-align:right}.tableWrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:9px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}th{color:#555;background:#fafafa;position:sticky;top:0}.num{text-align:right;white-space:nowrap}.rank{font-weight:900;color:var(--orange)}.warnBox{background:#fff8e6;border:1px solid #f5d47a;border-radius:12px;padding:12px;margin-top:10px}.empty{padding:20px;text-align:center;color:var(--muted)}
.tabs{display:flex;gap:8px;margin:14px 0 0}.tabs button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 12px;cursor:pointer}.tabs button.active{background:var(--orange);color:#fff;border-color:var(--orange)}
@media(max-width:900px){.kpis,.sources,.grid2,.grid3{grid-template-columns:1fr 1fr}.top .wrap{align-items:flex-start;flex-direction:column}}@media(max-width:580px){.kpis,.sources,.grid2,.grid3{grid-template-columns:1fr}.wrap{padding:10px}}
</style></head><body>
<div class="top"><div class="wrap"><div class="brand"><div class="logo">D</div><div><h1>Diligo E-commerce Dashboard</h1><small>Shopee · TikTok · Niva · Lipzo</small></div></div><div class="filters"><input id="fromDate" type="date"><span>→</span><input id="toDate" type="date"><select id="platform"><option value="All">Tổng 2 sàn</option><option>Shopee</option><option>TikTok</option></select><select id="brand"><option value="All">Tất cả nhãn</option><option>Lipzo</option><option>Niva</option></select><select id="source"></select><button id="apply">Áp dụng</button></div></div></div>
<div class="wrap">
  <div class="tabs"><button class="active" data-tab="overview">Tổng quan</button><button data-tab="marketing">Tiếp thị</button><button data-tab="finance">Tài chính</button><button data-tab="quality">Chất lượng dữ liệu</button></div>
  <div id="tab-overview">
    <div class="card section"><div class="sectionHead"><div><h2>Tổng quan</h2><small id="rangeLabel"></small></div><span id="coverageChip" class="chip ok">Dữ liệu</span></div><div id="kpis" class="kpis"></div></div>
    <div class="card section"><div class="sectionHead"><div><h2>Nguồn doanh số</h2><small>GMV và tỷ trọng % theo từng nguồn</small></div></div><div id="sources" class="sources"></div><div id="sourceWarning"></div></div>
    <div class="grid2"><div class="card section"><div class="sectionHead"><div><h2>Ngành hàng</h2><small>Theo nguồn đang chọn</small></div></div><div id="categories"></div></div><div class="card section"><div class="sectionHead"><div><h2>Top sản phẩm / nội dung</h2><small>Theo GMV</small></div></div><div id="topItems"></div></div></div>
    <div class="card section"><div class="sectionHead"><div><h2>Diễn biến GMV theo ngày</h2><small>Không cộng khách hàng unique khi chọn nhiều ngày</small></div></div><div id="dailyTable" class="tableWrap"></div></div>
  </div>
  <div id="tab-marketing" style="display:none"><div class="card section"><div class="sectionHead"><div><h2>Quảng cáo</h2><small>Ads tách riêng khỏi nguồn bán hàng</small></div></div><div id="adsSummary" class="kpis"></div><div id="adsTable" class="tableWrap" style="margin-top:12px"></div></div></div>
  <div id="tab-finance" style="display:none"><div class="card section"><div class="sectionHead"><div><h2>Tài chính quyết toán</h2><small>Ngày Finance khác ngày bán hàng</small></div></div><div id="financeSummary" class="kpis"></div><div id="financeTable" class="tableWrap" style="margin-top:12px"></div></div></div>
  <div id="tab-quality" style="display:none"><div class="card section"><div class="sectionHead"><div><h2>Chất lượng & phạm vi dữ liệu</h2><small>Hệ thống không tự bịa dữ liệu khi thiếu file</small></div></div><div id="warnings"></div></div></div>
</div>
<script>
const DATA=__DATA__;
const $=q=>document.querySelector(q), $$=q=>[...document.querySelectorAll(q)];
const fmt=n=>n===null||n===undefined||Number.isNaN(Number(n))?'—':new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(Number(n));
const money=n=>n===null||n===undefined?'—':'₫'+new Intl.NumberFormat('vi-VN',{maximumFractionDigits:0}).format(Number(n));
const compact=n=>{if(n===null||n===undefined)return'—';n=Number(n);if(Math.abs(n)>=1e9)return (n/1e9).toFixed(2).replace('.',',')+' tỷ';if(Math.abs(n)>=1e6)return (n/1e6).toFixed(2).replace('.',',')+' tr';if(Math.abs(n)>=1e3)return (n/1e3).toFixed(1).replace('.',',')+'k';return fmt(n)};
const pct=n=>Number.isFinite(Number(n))?(Number(n)*100).toFixed(2).replace('.',',')+'%':'—';
const isoDate=s=>new Date(s+'T00:00:00');
const dateList=(a,b)=>{let out=[],d=isoDate(a),e=isoDate(b);while(d<=e){out.push(d.toISOString().slice(0,10));d.setDate(d.getDate()+1)}return out};
const sum=(arr,key)=>arr.reduce((a,x)=>a+(Number(x[key])||0),0);
const state={from:'',to:'',platform:'All',brand:'All',source:'Overall'};
const sourceDefs={All:['Overall','Thẻ sản phẩm','Phát trực tiếp','Video','Tiếp thị liên kết'],Shopee:['Overall','Thẻ sản phẩm','Phát trực tiếp','Video','Tiếp thị liên kết'],TikTok:['Overall','Thẻ sản phẩm','Phát trực tiếp','Video','Tiếp thị liên kết']};

function dailyRows(platform=state.platform){return DATA.daily.filter(r=>r.date>=state.from&&r.date<=state.to&&(platform==='All'||r.platform===platform))}
function exactSummary(platform){return DATA.overview_summaries.find(r=>r.platform===platform&&r.period_start===state.from&&r.period_end===state.to)}
function platformDaily(platform){return dailyRows(platform)}
function selectedPlatforms(){return state.platform==='All'?['Shopee','TikTok']:[state.platform]}

function periodKeys(records,platform,extraFn=()=>true){
  let cand=records.filter(r=>r.platform===platform&&r.period_start>=state.from&&r.period_end<=state.to&&extraFn(r));
  let keys=[...new Map(cand.map(r=>[r.period_start+'|'+r.period_end,{start:r.period_start,end:r.period_end}])).values()];
  keys.sort((a,b)=>((isoDate(a.end)-isoDate(a.start))-(isoDate(b.end)-isoDate(b.start))));
  const need=new Set(dateList(state.from,state.to)), used=new Set(), chosen=[];
  for(const k of keys){const ds=dateList(k.start,k.end);if(ds.some(d=>used.has(d)))continue;if(ds.every(d=>need.has(d))){chosen.push(k);ds.forEach(d=>used.add(d))}}
  return {chosen,coverage:need.size?used.size/need.size:0,covered:used.size,total:need.size};
}
function periodMatch(r,sel){return sel.chosen.some(k=>r.period_start===k.start&&r.period_end===k.end)}

function tiktokSources(){let rows=platformDaily('TikTok');let g=sum(rows,'gmv'),la=sum(rows,'live_aff'),ls=sum(rows,'live_seller'),va=sum(rows,'video_aff'),vs=sum(rows,'video_seller');return {'Overall':g,'Thẻ sản phẩm':Math.max(0,g-la-ls-va-vs),'Phát trực tiếp':ls,'Video':vs,'Tiếp thị liên kết':la+va}}
function shopeeSourceValue(source){let sel=periodKeys(DATA.source_periods,'Shopee',r=>r.source===source);let rows=DATA.source_periods.filter(r=>r.source===source&&periodMatch(r,sel));return {value:sum(rows,'gmv'),coverage:sel.coverage}}
function sourceValues(platform){
  if(platform==='TikTok')return {vals:tiktokSources(),coverage:1};
  if(platform==='Shopee'){let vals={},cov=1;for(const s of sourceDefs.Shopee){if(s==='Overall')continue;let x=shopeeSourceValue(s);vals[s]=x.value;cov=Math.min(cov,x.coverage)}vals.Overall=Object.values(vals).reduce((a,b)=>a+b,0);return {vals,coverage:cov}}
  let sh=sourceValues('Shopee'),tt=sourceValues('TikTok'),vals={};for(const s of sourceDefs.All){vals[s]=(sh.vals[s]||0)+(tt.vals[s]||0)}return {vals,coverage:Math.min(sh.coverage,tt.coverage)};
}

function renderFilters(){let defs=sourceDefs[state.platform];$('#source').innerHTML=defs.map(s=>`<option value="${s}">${s==='Overall'?'Tổng nguồn':s}</option>`).join('');$('#source').value=state.source;if(!defs.includes(state.source)){state.source='Overall';$('#source').value='Overall'}}
function renderKPIs(){
  let rows=dailyRows(),gmv=sum(rows,'gmv'),orders=sum(rows,'orders');let sh=platformDaily('Shopee'),tt=platformDaily('TikTok');
  let customer='—';if(state.from===state.to)customer=fmt(sum(rows,'customers'));else if(state.platform!=='All'){let ex=exactSummary(state.platform);if(ex)customer=fmt(ex.customers)}
  let aov='—';if(state.platform==='Shopee')aov=money(sum(sh,'gmv')/(sum(sh,'orders')||1));if(state.platform==='TikTok')aov=money(sum(tt,'gmv')/(sum(tt,'sku_orders')||1));
  let clicks=sum(rows,'product_clicks'),vis=sum(rows,'visitors'),cvr=null,cvrNote='';
  if(state.platform==='Shopee'){cvr=clicks?sum(sh,'orders')/clicks:null;cvrNote='Shopee: đơn xác nhận / click sản phẩm'}
  else if(state.platform==='TikTok'){if(state.from===state.to&&tt.length)cvr=tt[0].cvr;else{let ex=exactSummary('TikTok');if(ex)cvr=ex.cvr??null}cvrNote='TikTok: theo chỉ số CR trong Shop Analytics'}
  else cvrNote='Không gộp CR của 2 sàn';
  let cards=[['GMV',money(gmv),state.platform==='All'?'Tổng hai sàn':state.platform],['Đơn hàng',fmt(orders),'Shopee xác nhận / TikTok orders'],['AOV',aov,state.platform==='All'?'Không gộp AOV 2 sàn':'Theo denominator của sàn'],['Khách hàng',customer,state.from===state.to?'Unique ngày':'Không cộng daily unique'],['Click sản phẩm',fmt(clicks),''],['Khách truy cập',fmt(vis),''],['CR',cvr===null?'—':pct(cvr),cvrNote]];
  $('#kpis').innerHTML=cards.map(x=>`<div class="card kpi"><div class="lab">${x[0]}</div><div class="val">${x[1]}</div><div class="sub">${x[2]}</div></div>`).join('');
  $('#rangeLabel').textContent=`${state.from} → ${state.to}`;
}
function renderSources(){let x=sourceValues(state.platform),vals=x.vals,total=vals.Overall||0;let defs=sourceDefs[state.platform];$('#sources').innerHTML=defs.map(s=>{let v=vals[s]||0,share=s==='Overall'?1:(total?v/total:0);return `<div class="card source ${state.source===s?'active':''}" data-source="${s}"><div class="shead"><span class="sname">${s==='Overall'?'Tổng nguồn':s}</span><span class="sshare">${pct(share)}</span></div><div class="sval">${compact(v)}</div><div class="bar"><i style="width:${Math.min(100,share*100)}%"></i></div><div class="foot">${s==='Overall'?'100% nguồn bán hàng':'Tỷ trọng trên tổng nguồn'}</div></div>`}).join('');$$('#sources .source').forEach(el=>el.onclick=()=>{state.source=el.dataset.source;$('#source').value=state.source;renderAll()});$('#sourceWarning').innerHTML=x.coverage<.999?`<div class="warnBox">⚠️ Nguồn Shopee chưa đủ dữ liệu chi tiết cho toàn bộ khoảng đang chọn (${pct(x.coverage)} ngày được phủ). Hệ thống không nội suy phần thiếu.</div>`:''}
function selectedProductFacts(){let platforms=selectedPlatforms(),out=[];for(const p of platforms){let wanted=state.source;if(wanted==='Overall'){for(const s of SOURCE_ORDER){let sel=periodKeys(DATA.product_facts,p,r=>r.source===s);out.push(...DATA.product_facts.filter(r=>r.platform===p&&r.source===s&&periodMatch(r,sel)))}}else{let sel=periodKeys(DATA.product_facts,p,r=>r.source===wanted);out.push(...DATA.product_facts.filter(r=>r.platform===p&&r.source===wanted&&periodMatch(r,sel)))}}if(state.brand!=='All')out=out.filter(r=>r.brand===state.brand);return out}
function renderCategories(){let rows=selectedProductFacts(),m={};for(const r of rows){let k=r.category||'CHƯA GÁN';if(!m[k])m[k]={gmv:0,orders:0};m[k].gmv+=+r.gmv||0;m[k].orders+=+r.orders||0}let arr=Object.entries(m).sort((a,b)=>b[1].gmv-a[1].gmv),tot=arr.reduce((a,x)=>a+x[1].gmv,0);if(!arr.length){$('#categories').innerHTML='<div class="empty">Nguồn này chưa có dữ liệu ngành/sản phẩm ở kỳ đang chọn.</div>';return}$('#categories').innerHTML=arr.slice(0,12).map(([k,v])=>`<div class="metric"><span>${k}<div class="bar"><i style="width:${tot?v.gmv/tot*100:0}%"></i></div></span><b>${money(v.gmv)}<div class="foot">${pct(tot?v.gmv/tot:0)}</div></b></div>`).join('')}
function renderTopItems(){let rows=selectedProductFacts();let by={};for(const r of rows){let k=(r.product_id||'')+'|'+(r.product_name||'');if(!by[k])by[k]={name:r.product_name,gmv:0,orders:0,cat:r.category};by[k].gmv+=+r.gmv||0;by[k].orders+=+r.orders||0}let arr=Object.values(by).sort((a,b)=>b.gmv-a.gmv).slice(0,10);let html='';if(arr.length)html+=`<table><thead><tr><th>#</th><th>Sản phẩm</th><th>Ngành</th><th class="num">GMV</th><th class="num">Đơn</th></tr></thead><tbody>${arr.map((x,i)=>`<tr><td class="rank">${i+1}</td><td>${esc(x.name)}</td><td>${x.cat}</td><td class="num">${money(x.gmv)}</td><td class="num">${fmt(x.orders)}</td></tr>`).join('')}</tbody></table>`;
  // Top content theo source
  let kinds=[];if(state.platform!=='TikTok'&&state.source==='Video')kinds=['video'];if(state.platform!=='TikTok'&&state.source==='Phát trực tiếp')kinds=['live'];if(state.platform!=='TikTok'&&state.source==='Tiếp thị liên kết')kinds=['affiliate'];if(state.platform!=='Shopee'&&state.source==='Video')kinds.push('video');if(state.platform!=='Shopee'&&state.source==='Phát trực tiếp')kinds.push('live');if(state.platform!=='Shopee'&&state.source==='Tiếp thị liên kết')kinds.push('affiliate_video','affiliate_live');
  if(kinds.length){let items=[];for(const p of selectedPlatforms()){for(const k of kinds){let sel=periodKeys(DATA.content_periods,p,r=>r.kind===k);for(const per of DATA.content_periods.filter(r=>r.platform===p&&r.kind===k&&periodMatch(r,sel)))items.push(...per.items)}}let b={};for(const x of items){let isTTLAff=x.platform==='TikTok'&&(x.kind==='affiliate_video'||x.kind==='affiliate_live');let key=isTTLAff?(x.platform+'|affiliate|'+(x.creator||x.item_id||x.title)):(x.platform+'|'+x.kind+'|'+(x.item_id||x.creator||x.title));if(!b[key])b[key]={title:x.title,creator:x.creator,gmv:0,orders:0};b[key].gmv+=+x.gmv||0;b[key].orders+=+x.orders||0}let top=Object.values(b).sort((a,b)=>b.gmv-a.gmv).slice(0,8);if(top.length)html+=`<div style="margin-top:14px"><b>Top nội dung / KOC-KOL</b><table><thead><tr><th>#</th><th>Nội dung / Creator</th><th class="num">GMV</th><th class="num">Đơn</th></tr></thead><tbody>${top.map((x,i)=>`<tr><td class="rank">${i+1}</td><td>${esc(x.creator||x.title)}<div class="foot">${esc((x.title||'').slice(0,90))}</div></td><td class="num">${money(x.gmv)}</td><td class="num">${fmt(x.orders)}</td></tr>`).join('')}</tbody></table></div>`}
  $('#topItems').innerHTML=html||'<div class="empty">Chưa có dữ liệu phù hợp.</div>'}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function renderDaily(){let rows=dailyRows();let dates=[...new Set(rows.map(r=>r.date))].sort();let html=`<table><thead><tr><th>Ngày</th><th class="num">GMV</th><th class="num">Đơn</th><th class="num">Hoàn tiền</th><th class="num">Hủy GMV</th></tr></thead><tbody>`;for(const d of dates){let rr=rows.filter(x=>x.date===d);html+=`<tr><td>${d}</td><td class="num">${money(sum(rr,'gmv'))}</td><td class="num">${fmt(sum(rr,'orders'))}</td><td class="num">${money(sum(rr,'refund'))}</td><td class="num">${money(sum(rr,'cancel_gmv'))}</td></tr>`}html+='</tbody></table>';$('#dailyTable').innerHTML=dates.length?html:'<div class="empty">Không có dữ liệu ngày trong khoảng này.</div>'}
function selectedAds(){let arr=[];for(const p of selectedPlatforms()){let sel=periodKeys(DATA.ads,p,()=>true);arr.push(...DATA.ads.filter(r=>r.platform===p&&periodMatch(r,sel)))}return arr}
function renderAds(){
  let rows=selectedAds();
  // Summary theo từng sàn để không cộng Shopee headline với các report thành phần.
  let sumRows=[];let notes=[];
  for(const p of selectedPlatforms()){
    let pr=rows.filter(r=>r.platform===p);
    if(p==='Shopee'){
      let hd=pr.filter(r=>r.headline===true||r.headline==='True'||r.headline==='true');
      if(hd.length){sumRows.push(...hd);notes.push('Shopee: dùng headline Ads chính thức')}
      else{sumRows.push(...pr);if(pr.length)notes.push('Shopee: GMV là tổng các report thành phần, có thể chồng attribution')}
    }else sumRows.push(...pr);
  }
  let cost=sum(sumRows,'cost'),gmv=sum(sumRows,'gmv'),orders=sum(sumRows,'orders');
  let cards=[['Chi phí Ads',money(cost),'Theo report đã chọn'],['GMV ghi nhận',money(gmv),notes.join(' · ')||'Theo report Ads'],['Đơn Ads',fmt(orders),'Theo report Ads'],['ROAS ghi nhận',cost?fmt(gmv/cost)+'x':'—','Không dùng để thay GMV bán hàng']];
  $('#adsSummary').innerHTML=cards.map(x=>`<div class="card kpi"><div class="lab">${x[0]}</div><div class="val">${x[1]}</div><div class="sub">${x[2]}</div></div>`).join('');
  let by={};for(const r of rows){let k=r.platform+'|'+(r.campaign||r.subtype||'Ads');if(!by[k])by[k]={platform:r.platform,name:r.campaign||r.subtype,cost:0,gmv:0,orders:0};by[k].cost+=+r.cost||0;by[k].gmv+=+r.gmv||0;by[k].orders+=+r.orders||0}
  let arr=Object.values(by).sort((a,b)=>b.gmv-a.gmv);$('#adsTable').innerHTML=arr.length?`<table><thead><tr><th>Sàn</th><th>Chiến dịch/nhánh</th><th class="num">Chi phí</th><th class="num">GMV ghi nhận</th><th class="num">Đơn</th><th class="num">ROAS</th></tr></thead><tbody>${arr.map(x=>`<tr><td>${x.platform}</td><td>${esc(x.name)}</td><td class="num">${money(x.cost)}</td><td class="num">${money(x.gmv)}</td><td class="num">${fmt(x.orders)}</td><td class="num">${x.cost?fmt(x.gmv/x.cost)+'x':'—'}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">Không có Ads trong kỳ.</div>'}
function selectedFinance(){let out=[];for(const p of selectedPlatforms()){let sel=periodKeys(DATA.finance,p,()=>true);out.push(...DATA.finance.filter(r=>r.platform===p&&periodMatch(r,sel)))}return out}
function renderFinance(){let rows=selectedFinance(),rev=sum(rows,'revenue'),cost=sum(rows,'cost'),adj=sum(rows,'adjustment'),payout=sum(rows,'payout');let cards=[['Doanh thu quyết toán',money(rev),''],['Tổng phí',money(cost),rev?pct(cost/rev):'—'],['Điều chỉnh',money(adj),rev?pct(adj/rev):'—'],['Tiền về',money(payout),rev?pct(payout/rev):'—']];$('#financeSummary').innerHTML=cards.map(x=>`<div class="card kpi"><div class="lab">${x[0]}</div><div class="val">${x[1]}</div><div class="sub">${x[2]}</div></div>`).join('');$('#financeTable').innerHTML=rows.length?`<table><thead><tr><th>Sàn</th><th>Kỳ quyết toán</th><th class="num">Doanh thu</th><th class="num">Phí</th><th class="num">Điều chỉnh</th><th class="num">Tiền về</th></tr></thead><tbody>${rows.sort((a,b)=>a.period_start.localeCompare(b.period_start)).map(x=>`<tr><td>${x.platform}</td><td>${x.period_start}${x.period_end!==x.period_start?' → '+x.period_end:''}</td><td class="num">${money(x.revenue)}</td><td class="num">${money(x.cost)}</td><td class="num">${money(x.adjustment)}</td><td class="num">${money(x.payout)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">Không có Finance trong kỳ.</div>'}
function renderWarnings(){let msgs=[...DATA.warnings];let sh=sourceValues('Shopee');if(sh.coverage<.999)msgs.push(`Nguồn Shopee chỉ phủ ${pct(sh.coverage)} khoảng ngày đang chọn.`);$('#warnings').innerHTML=msgs.length?msgs.map(x=>`<div class="warnBox">⚠️ ${esc(x)}</div>`).join(''):'<div class="chip ok">Không phát hiện cảnh báo quan trọng.</div>'}
function renderAll(){renderFilters();renderKPIs();renderSources();renderCategories();renderTopItems();renderDaily();renderAds();renderFinance();renderWarnings();$('#coverageChip').textContent='Đã nạp '+DATA.daily.length+' dòng daily'}
function init(){let dates=DATA.daily.map(r=>r.date).sort();if(!dates.length){let today=new Date().toISOString().slice(0,10);dates=[today]}state.from=dates[0];state.to=dates[dates.length-1];$('#fromDate').value=state.from;$('#toDate').value=state.to;$('#platform').value=state.platform;$('#brand').value=state.brand;renderFilters();$('#apply').onclick=()=>{state.from=$('#fromDate').value;state.to=$('#toDate').value;state.platform=$('#platform').value;state.brand=$('#brand').value;state.source=$('#source').value;renderAll()};$('#platform').onchange=()=>{state.platform=$('#platform').value;state.source='Overall';renderFilters()};$$('.tabs button').forEach(b=>b.onclick=()=>{$$('.tabs button').forEach(x=>x.classList.remove('active'));b.classList.add('active');['overview','marketing','finance','quality'].forEach(t=>$('#tab-'+t).style.display=t===b.dataset.tab?'block':'none')});renderAll()}
init();
</script></body></html>'''


def build_html(data:dict,out_path:Path)->None:
    # Remove nested products duplication in source_periods before embed (product_facts already contains detail)
    slim=dict(data)
    slim["source_periods"]=[{k:v for k,v in r.items() if k!="products"} for r in data["source_periods"]]
    txt=HTML_TEMPLATE.replace("__DATA__",json.dumps(slim,ensure_ascii=False,separators=(",",":")))
    out_path.write_text(txt,encoding="utf-8")



# -------------------------
# V25 COMPATIBILITY LAYER
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
V25_BASELINE_FILE = BASE_DIR / "baseline_v25.json"
V25_TEMPLATE_FILE = BASE_DIR / "dashboard_template_v25.html"


def _v25_source_name(platform: str, source: str) -> str:
    if platform == "Shopee":
        return {"Thẻ sản phẩm":"Product Card","Phát trực tiếp":"Live","Video":"Video","Tiếp thị liên kết":"Affiliate"}.get(source, source)
    return {"Thẻ sản phẩm":"Product Card","Phát trực tiếp":"Live Official","Video":"Video Official","Tiếp thị liên kết":"Video Affiliate"}.get(source, source)


def _merge_by_key(old: list[dict], new: list[dict], key_fn):
    m = {key_fn(r): r for r in old}
    for r in new:
        m[key_fn(r)] = r
    return list(m.values())


def _v25_categories_products(raw: dict) -> tuple[list[dict], list[dict]]:
    facts = raw.get("product_facts", [])
    groups: dict[tuple, dict] = {}
    product_groups: dict[tuple, dict] = {}
    for x in facts:
        p=x.get("platform") or ""
        src=_v25_source_name(p, x.get("source") or "")
        a=x.get("period_start") or ""; b=x.get("period_end") or a
        brand=x.get("brand") or "CHƯA GÁN"; cat=x.get("category") or "CHƯA GÁN"
        k=(p,src,a,b,brand,cat)
        g=groups.setdefault(k,{"platform":p,"source":src,"start":a,"end":b,"brand":brand,"category":cat,"gmv":0.0,"orders":0.0,"units":0.0,"quality":"Exact product-level · auto","usable":True,"coverage":1.0})
        g["gmv"] += float(x.get("gmv") or 0); g["orders"] += float(x.get("orders") or 0); g["units"] += float(x.get("units") or 0)
        pk=(p,src,a,b,brand,cat,str(x.get("product_id") or ""),x.get("product_name") or "")
        q=product_groups.setdefault(pk,{"platform":p,"source":src,"start":a,"end":b,"brand":brand,"category":cat,"pid":str(x.get("product_id") or ""),"name":x.get("product_name") or "","gmv":0.0,"orders":0.0,"units":0.0,"impressions":0.0,"clicks":0.0,"quality":"Exact product-level · auto","coverage":1.0})
        q["gmv"] += float(x.get("gmv") or 0); q["orders"] += float(x.get("orders") or 0); q["units"] += float(x.get("units") or 0); q["impressions"] += float(x.get("impressions") or 0); q["clicks"] += float(x.get("clicks") or 0)
    cats=list(groups.values())
    # share/rank inside exact platform/source/period
    buckets={}
    for r in cats:buckets.setdefault((r["platform"],r["source"],r["start"],r["end"]),[]).append(r)
    for rr in buckets.values():
        rr.sort(key=lambda z:z["gmv"],reverse=True); tot=sum(z["gmv"] for z in rr) or 1
        for i,z in enumerate(rr,1):z["share"]=z["gmv"]/tot;z["rank"]=i
    prods=list(product_groups.values())
    pb={}
    for r in prods:pb.setdefault((r["platform"],r["source"],r["start"],r["end"],r["brand"],r["category"]),[]).append(r)
    for rr in pb.values():
        rr.sort(key=lambda z:z["gmv"],reverse=True);tot=sum(z["gmv"] for z in rr) or 1
        for i,z in enumerate(rr,1):
            z["share_cat"]=z["gmv"]/tot;z["rank"]=i
            z["ctr"]=(z.get("clicks") or 0)/(z.get("impressions") or 1) if z.get("impressions") else None
            z["cvr"]=(z.get("orders") or 0)/(z.get("clicks") or 1) if z.get("clicks") else None
            z["aov"]=(z.get("gmv") or 0)/(z.get("orders") or 1) if z.get("orders") else None
    return cats,prods


def _v25_content(raw: dict) -> dict[str,list[dict]]:
    out={"top_videos_shopee":[],"top_live_shopee":[],"top_videos_tiktok_official":[],"top_live_tiktok_official":[],"top_creators_tiktok_affiliate":[],"top_creators_shopee_affiliate":[]}
    # records are period-scoped; keep period fields so HTML date filter can select them.
    for p in raw.get("content_periods",[]):
        a=p.get("period_start");b=p.get("period_end") or a;plat=p.get("platform");kind=p.get("kind")
        items=p.get("items",[])
        if plat=="Shopee" and kind=="video":
            total=sum(float(x.get("gmv") or 0) for x in items) or 1
            for x in items:
                out["top_videos_shopee"].append({"start":a,"end":b,"video_id":x.get("item_id"),"video":x.get("title"),"share":float(x.get("gmv") or 0)/total,"gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"cvr":0})
        elif plat=="Shopee" and kind=="live":
            for x in items:
                out["top_live_shopee"].append({"start":a,"end":b,"session_id":x.get("item_id"),"session":x.get("title"),"gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0)})
        elif plat=="TikTok" and kind=="video":
            for x in items:
                out["top_videos_tiktok_official"].append({"start":a,"end":b,"creator":x.get("creator"),"video_id":x.get("item_id"),"video_info":x.get("title"),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"orders":float(x.get("orders") or 0),"gmv":float(x.get("gmv") or 0)})
        elif plat=="TikTok" and kind=="live":
            for x in items:
                out["top_live_tiktok_official"].append({"start":a,"end":b,"creator":x.get("creator"),"session_id":x.get("item_id"),"session":x.get("title"),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"gmv":float(x.get("gmv") or 0)})
        elif plat=="TikTok" and kind in {"affiliate_video","affiliate_live"}:
            for x in items:
                nm=x.get("creator") or x.get("title") or x.get("item_id")
                out["top_creators_tiktok_affiliate"].append({"start":a,"end":b,"creator_id":nm,"name":nm,"nickname":"","total_gmv":float(x.get("gmv") or 0),"video_gmv":float(x.get("gmv") or 0) if kind=="affiliate_video" else 0.0,"live_gmv":float(x.get("gmv") or 0) if kind=="affiliate_live" else 0.0,"orders":float(x.get("orders") or 0),"videos":1 if kind=="affiliate_video" else 0,"live_sessions":1 if kind=="affiliate_live" else 0,"clicks":float(x.get("clicks") or 0),"views":float(x.get("views") or 0)})
        elif plat=="Shopee" and kind in {"affiliate","affiliate_video","affiliate_live"}:
            for x in items:
                nm=x.get("creator") or x.get("title") or x.get("item_id")
                # Keep only rows that actually have attributed GMV/orders for ranking.
                if float(x.get("gmv") or 0)<=0 and float(x.get("orders") or 0)<=0: continue
                channel = x.get("affiliate_channel") or ("Video" if kind=="affiliate_video" else "Live" if kind=="affiliate_live" else None)
                out["top_creators_shopee_affiliate"].append({"start":a,"end":b,"creator_id":nm,"name":nm,"channel":channel,"total_gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0)})
    return out


def build_v25_data(raw: dict) -> dict:
    base=json.loads(V25_BASELINE_FILE.read_text(encoding="utf-8"))
    # Daily: raw file for a date wins over historical embedded record.
    base["daily"]=_merge_by_key(base.get("daily",[]),raw.get("daily",[]),lambda r:(r.get("platform"),r.get("date")))
    base["daily"].sort(key=lambda r:(r.get("date") or "",r.get("platform") or ""))

    # Exact Overview period summaries are useful for week/month comparison (especially CVR/unique metrics).
    # Raw/history wins for the same platform + exact period.
    overview_fresh=[]
    for r in raw.get("overview_summaries",[]):
        overview_fresh.append({
            "platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),
            "gmv":float(r.get("gmv") or 0),"orders":float(r.get("orders") or 0),
            "sku_orders":float(r.get("sku_orders") or 0),"customers":r.get("customers"),
            "cvr":r.get("cvr"),"refund":float(r.get("refund") or 0),
            "cancel_gmv":r.get("cancel_gmv"),"cancel_orders":r.get("cancel_orders"),
            "refund_orders":r.get("refund_orders"),"source_file":r.get("source_file")
        })
    base["overview_periods"]=_merge_by_key(base.get("overview_periods",[]),overview_fresh,lambda r:(r.get("platform"),r.get("period_start"),r.get("period_end")))

    # Source periods: only Shopee needs period-aware source table; raw wins same period/source.
    fresh=[]
    for r in raw.get("source_periods",[]):
        if r.get("platform")!="Shopee": continue
        fresh.append({"platform":"Shopee","source":_v25_source_name("Shopee",r.get("source") or ""),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"gmv":float(r.get("gmv") or 0),"orders":r.get("orders"),"units":r.get("units"),"quality":"Auto từ file raw"})
    base["source_periods"]=_merge_by_key(base.get("source_periods",[]),fresh,lambda r:(r.get("platform"),r.get("source"),r.get("period_start"),r.get("period_end")))

    cats,prods=_v25_categories_products(raw)
    base["categories"]=_merge_by_key(base.get("categories",[]),cats,lambda r:(r.get("platform"),r.get("source"),r.get("start"),r.get("end"),r.get("brand"),r.get("category")))
    base["products"]=_merge_by_key(base.get("products",[]),prods,lambda r:(r.get("platform"),r.get("source"),r.get("start"),r.get("end"),r.get("brand"),r.get("category"),str(r.get("pid") or ""),r.get("name")))

    ct=_v25_content(raw)
    for key,arr in ct.items():
        old=base.get(key,[])
        # Replace whole same platform-kind periods implicitly by period+item id/name.
        if key=="top_videos_shopee": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("video_id") or ""))
        elif key=="top_live_shopee": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("session_id") or ""))
        elif key=="top_videos_tiktok_official": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("video_id") or ""))
        elif key=="top_live_tiktok_official": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("session_id") or r.get("creator") or ""))
        elif key=="top_creators_shopee_affiliate": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("creator_id") or r.get("name") or ""),r.get("channel"))
        else: kf=lambda r:(r.get("start"),r.get("end"),str(r.get("creator_id") or r.get("name") or ""))
        base[key]=_merge_by_key(old,arr,kf)

    # Ads periods. Remove same platform/period raw groups then append raw detail; this prevents baseline day15 summary + raw detail double count.
    raw_ads=raw.get("ads",[])
    if raw_ads:
        periods={(r.get("platform"),r.get("period_start"),r.get("period_end")) for r in raw_ads}
        keep=[r for r in base.get("ads_periods",[]) if (r.get("platform"),r.get("period_start"),r.get("period_end")) not in periods]
        for r in raw_ads:
            rr={"platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"subtype":r.get("subtype") or "Ads","campaign":r.get("campaign") or r.get("subtype") or "Ads","cost":float(r.get("cost") or 0),"gmv":float(r.get("gmv") or 0),"orders":r.get("orders"),"headline":bool(r.get("headline")),"note":"Auto từ file raw", **{k:r[k] for k in ("daily_rows","detail_status","detail_note","detail_count","detail_payout","source_file","source_mtime","grain","campaign_id") if k in r}}
            keep.append(rr)
        base["ads_periods"]=keep

    # Shopee internal traffic sources at daily grain; raw/history wins by date + source.
    base["shopee_traffic_daily"]=_merge_by_key(
        base.get("shopee_traffic_daily",[]), raw.get("traffic_daily",[]),
        lambda r:(r.get("date"),r.get("main_source"),r.get("traffic_source"))
    )
    _traffic_allowed = {
        "Product Card": {"Thẻ sản phẩm","Tìm kiếm","Đề xuất","Cửa hàng","Đơn mua của tôi","Giỏ hàng","Khuyến mãi","Chat","Khác"},
        "Live": {"Live","Cửa hàng","Giỏ hàng","Đề xuất","Tìm kiếm","Đơn mua của tôi","Video","Thẻ Live","Trang chủ Shopee Live","Chat","Khác"},
        "Video": {"Video","Tìm kiếm","Đề xuất","Cửa hàng","Giỏ hàng","Đơn mua của tôi","Thẻ Video","Video nổi bật","Trang chủ Shopee Video","Chat","Hồ sơ người tạo","Khác"},
        "Affiliate": {"Tiếp thị liên kết","Affiliate Video","Affiliate Live","Khác"},
    }
    base["shopee_traffic_daily"]=[r for r in base["shopee_traffic_daily"] if r.get("traffic_source") in _traffic_allowed.get(r.get("main_source"), set())]
    base["shopee_traffic_daily"].sort(key=lambda r:(r.get("date") or "",r.get("main_source") or "",r.get("traffic_source") or ""))

    raw_fin=raw.get("finance",[])
    if raw_fin:
        periods={(r.get("platform"),r.get("period_start"),r.get("period_end")) for r in raw_fin}
        keep=[r for r in base.get("finance_periods",[]) if (r.get("platform"),r.get("period_start"),r.get("period_end")) not in periods]
        for r in raw_fin:
            keep.append({"platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"revenue":float(r.get("revenue") or 0),"cost":abs(float(r.get("cost") or 0)),"adjustment":abs(float(r.get("adjustment") or 0)),"payout":float(r.get("payout") or 0),"note":"Auto từ file raw", **{k:r[k] for k in ("daily_rows","detail_status","detail_note","detail_count","detail_payout","source_file","source_mtime","grain","campaign_id") if k in r}})
        base["finance_periods"]=keep
    base["warnings"]=raw.get("warnings",[])
    return base


def build_html_v25(raw: dict, out_path: Path, preferred_period: tuple[str,str] | None = None) -> None:
    data=build_v25_data(raw)
    txt=V25_TEMPLATE_FILE.read_text(encoding="utf-8").replace("__DATA__",json.dumps(data,ensure_ascii=False,separators=(",",":")))
    config_path = BASE_DIR / "AUTOMATION_CONFIG.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config.get("owners"), dict) or not isinstance(config.get("deadlines"), dict) or not 0 < float(config.get("peak_share", 0)) <= 1:
        raise ValueError("AUTOMATION_CONFIG.json: kiểm tra owners, deadlines và peak_share (0–1)")
    txt = txt.replace("__AUTO_CONFIG__", json.dumps(config, ensure_ascii=False).replace("<", "\\u003c"))
    dates=sorted({r.get("date") for r in data.get("daily",[]) if r.get("date")})
    if dates:
        if preferred_period:
            mn,mx=preferred_period
        else:
            mx=dates[-1]
            latest_month=mx[:7]
            same_month=[d for d in dates if d.startswith(latest_month)]
            mn=same_month[0] if same_month else mx
        txt=txt.replace("const state={platform:'All',source:'Overall',brand:'All',category:null,from:'2026-09-01',to:'2026-09-16',page:'overview'};",f"const state={{platform:'All',source:'Overall',brand:'All',category:null,from:'{mn}',to:'{mx}',page:'overview'}};")
    out_path.write_text(txt,encoding="utf-8")

def main()->int:
    parser=argparse.ArgumentParser(description="Diligo Auto Dashboard")
    parser.add_argument("--input",default=str(DEFAULT_INPUT),help="Thư mục Data_Input")
    parser.add_argument("--output",default=str(DEFAULT_OUTPUT),help="Thư mục xuất báo cáo")
    args=parser.parse_args()
    input_root=Path(args.input)
    output=Path(args.output)
    if not input_root.exists():
        log(f"❌ Không tìm thấy Data_Input: {input_root}")
        log("Bạn có thể chạy: py Diligo_Auto_Dashboard.py --input D:\\Data_Input")
        return 1
    output.mkdir(parents=True,exist_ok=True)
    log("="*68);log("DILIGO AUTO DASHBOARD");log(f"Input : {input_root}");log(f"Output: {output}");log("="*68)
    try:
        current=collect_data(input_root)
        history_path=output/HISTORY_FILENAME
        history=load_history_store(history_path)
        data=merge_history_store(history,current)
        finance_status = ["KIỂM TRA NẠP DỮ LIỆU TÀI CHÍNH", "TikTok chỉ tách ngày khi chi tiết khớp tổng doanh thu, phí và tiền quyết toán. Xem cảnh báo đối soát bên dưới.", ""]
        for title, records in [("File tài chính vừa đọc", current.get("finance", [])), ("Tài chính trong kho lịch sử", data.get("finance", []))]:
            finance_status.append(title + ": " + str(len(records)) + " bản ghi")
            for r in sorted(records, key=lambda r: (r.get("platform", ""), r.get("period_start", ""))):
                finance_status.append(f"{r.get('platform')} | {r.get('period_start')} → {r.get('period_end')} | {r.get('source_file', '')}")
        finance_status += ["", "Cảnh báo nhập dữ liệu:"] + list(current.get("warnings", []))
        (output / "KIEM_TRA_NAP_TAI_CHINH.txt").write_text("\n".join(finance_status), encoding="utf-8")
        ads_status=["KIỂM TRA NẠP ADS", "File có cột Theo ngày: lấy ngày từng dòng. File không có: giữ tổng kỳ, không chia đều."]
        for r in current.get("ads", []):
            ads_status.append(f"{r.get('platform')} | {r.get('period_start')} → {r.get('period_end')} | {r.get('campaign')} | Chi phí {r.get('cost')} | {r.get('source_file')}")
        ads_status += ["", "Cảnh báo:"] + list(current.get("warnings", []))
        (output / "KIEM_TRA_NAP_ADS.txt").write_text("\n".join(ads_status),encoding="utf-8")
        preferred=preferred_report_period(current,data)

        # CSV chuẩn hóa cho Power BI: luôn xuất từ kho lịch sử đã ghép.
        data_out=output/"Data_Output";data_out.mkdir(exist_ok=True)
        write_csv(data_out/"Sales_Daily.csv",data["daily"])
        write_csv(data_out/"Overview_Period.csv",data["overview_summaries"])
        write_csv(data_out/"Source_Period.csv",flatten_source_periods(data["source_periods"]))
        write_csv(data_out/"Source_Product.csv",data["product_facts"])
        write_csv(data_out/"Content.csv",flatten_content(data["content_periods"]))
        write_csv(data_out/"Shopee_Traffic_Daily.csv",data["traffic_daily"])
        write_csv(data_out/"Ads.csv",data["ads"])
        write_csv(data_out/"Finance.csv",data["finance"])
        write_csv(data_out/"Warnings.csv",[{"warning":x} for x in data["warnings"]],["warning"])
        build_html_v25(data,output/"index.html",preferred)
        (output/"data_snapshot.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

        # Chỉ cập nhật kho lịch sử sau khi toàn bộ output đã tạo thành công.
        if history_path.exists():
            shutil.copy2(history_path, output/HISTORY_BACKUP_FILENAME)
        save_history_store(history_path,data)

        new_count=sum(len(current.get(k,[])) for k in ("daily","overview_summaries","source_periods","content_periods","traffic_daily","ads","finance"))
        log("")
        log(f"✅ XONG: {output/'index.html'}")
        log(f"✅ Kho lịch sử: {history_path}")
        log(f"✅ CSV cho Power BI: {data_out}")
        if preferred:
            log(f"✅ Kỳ mở mặc định: {preferred[0]} → {preferred[1]}")
        if new_count:
            log("✅ Dữ liệu mới đã được ghi vào kho lịch sử. Sau khi thấy dòng XONG này, bạn có thể xóa file raw trong Data_Input nếu muốn.")
        else:
            log("ℹ️ Data_Input không có dữ liệu mới; báo cáo được dựng lại từ kho lịch sử.")
        log(f"⚠️ Cảnh báo dữ liệu: {len(data['warnings'])}")
        for w in data["warnings"][:10]:log("   - "+w)
        return 0
    except Exception as e:
        log("❌ Script gặp lỗi:")
        log(str(e));traceback.print_exc()
        return 2

if __name__=="__main__":
    raise SystemExit(main())
