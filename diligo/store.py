# -*- coding: utf-8 -*-
"""Kho lịch sử (HistoryStore).

Từ bản 40 kho lịch sử nằm trong MỘT file: HistoryStore_v2.json, gồm 2 phần:

- "raw":      dữ liệu đọc từ file sàn qua các lần chạy (giống HistoryStore.json cũ).
- "baseline": dữ liệu nền đã nhúng từ các bản V25–V39 (tháng 08 và 01–16/09/2026),
              trước đây nằm ở file baseline_v25.json để cạnh script.

Lần đầu chạy bản mới, chương trình tự gộp HistoryStore.json + baseline_v25.json
thành HistoryStore_v2.json. Hai file cũ KHÔNG bị sửa hay xóa.
"""
from __future__ import annotations
import copy
import gzip
import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import (
    HISTORY_FILENAME, HISTORY_V2_FILENAME, BASELINE_FILENAME,
    BACKUP_DIRNAME, BACKUP_KEEP,
)

STORE_SCHEMA_VERSION = 2


class StoreError(RuntimeError):
    """Lỗi kho lịch sử: dừng chương trình, không ghi đè gì."""


def _empty_store() -> dict:
    return {
        "daily": [], "overview_summaries": [], "source_periods": [],
        "product_facts": [], "content_periods": [], "traffic_daily": [], "ads": [],
        "finance": [], "warnings": []
    }


def _normalize_raw(obj: dict) -> dict:
    """Chỉ giữ các mục đã biết; source_periods không lưu lại danh sách sản phẩm
    (đã có đầy đủ trong product_facts, trước đây bị lưu 2 lần)."""
    out = _empty_store()
    for k in out:
        if k == "warnings":
            continue
        v = obj.get(k, [])
        out[k] = v if isinstance(v, list) else []
    out["source_periods"] = [{k: v for k, v in r.items() if k != "products"} for r in out["source_periods"]]
    return out


def _read_json(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise StoreError(f"Không đọc được {path}: {e}") from e
    if not isinstance(obj, dict):
        raise StoreError(f"{path} không phải JSON object")
    return obj


def load_history_store(path: Path) -> dict:
    """Đọc HistoryStore.json kiểu cũ (V30–V39)."""
    if not path.exists():
        return _empty_store()
    return _normalize_raw(_read_json(path))


def find_baseline(search_dirs: list[Path]) -> Path | None:
    for d in search_dirs:
        p = Path(d) / BASELINE_FILENAME
        if p.exists():
            return p
    return None


def load_store(output_dir: Path, baseline_search_dirs: list[Path]) -> tuple[dict, list[str]]:
    """Trả về (store, ghi_chú).

    store = {"raw": {...}, "baseline": {...}}.
    - Có HistoryStore_v2.json: đọc file này, không cần baseline_v25.json nữa.
    - Chưa có: gộp HistoryStore.json (nếu có) + baseline_v25.json (bắt buộc nếu đã từng
      chạy bản cũ) rồi trả về; file v2 chỉ được ghi khi cả lần chạy thành công.
    """
    v2 = output_dir / HISTORY_V2_FILENAME
    notes: list[str] = []
    if v2.exists():
        obj = _read_json(v2)
        if obj.get("schema_version") != STORE_SCHEMA_VERSION:
            raise StoreError(f"{v2}: schema_version không hợp lệ ({obj.get('schema_version')})")
        baseline = obj.get("baseline")
        if not isinstance(baseline, dict):
            raise StoreError(f"{v2}: thiếu phần baseline")
        return {"raw": _normalize_raw(obj.get("raw") or {}), "baseline": baseline}, notes

    v1 = output_dir / HISTORY_FILENAME
    bpath = find_baseline(baseline_search_dirs)
    if bpath is None:
        if v1.exists():
            dirs = "\n   - ".join(str(Path(d)) for d in baseline_search_dirs)
            raise StoreError(
                "Lần đầu chạy bản mới cần file baseline_v25.json để gộp lịch sử cũ (tháng 08 và 01–16/09).\n"
                "Hãy chép baseline_v25.json từ thư mục bản V39 vào một trong các thư mục:\n   - " + dirs +
                "\nChưa ghi gì vào kho lịch sử."
            )
        baseline = {}
        notes.append("Không có baseline_v25.json và chưa có lịch sử cũ: tạo kho mới trống.")
    else:
        baseline = _read_json(bpath)
        notes.append(f"Gộp baseline: {bpath}")
    raw = load_history_store(v1)
    if v1.exists():
        notes.append(f"Gộp lịch sử cũ: {v1} (file cũ giữ nguyên, không sửa)")
    notes.append(f"Lần đầu dùng kho mới: sẽ tạo {v2}")
    return {"raw": raw, "baseline": baseline}, notes


def _rotate_backups(output_dir: Path, current: Path) -> Path | None:
    if not current.exists():
        return None
    bdir = output_dir / BACKUP_DIRNAME
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = bdir / f"{current.stem}_{stamp}.json.gz"
    with current.open("rb") as src, gzip.open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst)
    old = sorted(bdir.glob(f"{current.stem}_*.json.gz"))
    for p in old[:-BACKUP_KEEP]:
        p.unlink()
    return dest


def save_store(output_dir: Path, raw: dict, baseline: dict) -> Path | None:
    """Ghi HistoryStore_v2.json (ghi file tạm rồi đổi tên, tránh hỏng file khi mất điện).
    Bản trước được nén vào thư mục HistoryStore_backups (giữ BACKUP_KEEP bản gần nhất)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / HISTORY_V2_FILENAME
    backup = _rotate_backups(output_dir, path)
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "_meta": {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "note": "Kho lịch sử Diligo. Không xóa file này nếu muốn giữ dữ liệu đã import.",
        },
        "raw": {k: v for k, v in _normalize_raw(raw).items() if k != "warnings"},
        "baseline": baseline,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return backup


def baseline_copy(store: dict) -> dict:
    """Bản sao độc lập để bước dựng dashboard không làm thay đổi kho."""
    return copy.deepcopy(store.get("baseline") or {})


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

