# -*- coding: utf-8 -*-
"""Đọc các file xuất từ Shopee Seller Center."""
from __future__ import annotations
import csv
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ..utils import (
    find_header_row, iso, last_numeric_in_row, parse_date_any, parse_period_text,
    period_from_filename, row_to_dict, safe_float, safe_float_dot, safe_pct, unique_headers,
)
from ..xlsx import xlsx_read_sheet
from ..taxonomy import classify_product

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

