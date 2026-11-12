# -*- coding: utf-8 -*-
"""Tiện ích chung: ép kiểu số kiểu Việt Nam, đọc ngày/kỳ, tìm dòng tiêu đề."""
from __future__ import annotations
import math
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable

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

