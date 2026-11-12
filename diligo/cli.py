# -*- coding: utf-8 -*-
"""Luồng chạy chính: đọc Data_Input -> ghép kho lịch sử -> xuất CSV + index.html -> lưu kho."""
from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from . import __version__
from .config import DEFAULT_INPUT, DEFAULT_OUTPUT, HISTORY_V2_FILENAME
from .collect import collect_data
from .dashboard import PROJECT_DIR, build_dashboard_data, load_automation_config, render_html
from .export_csv import flatten_content, flatten_source_periods, write_csv
from .store import (
    StoreError, baseline_copy, load_store, merge_history_store, preferred_report_period, save_store,
)
from .utils import log


def write_check_files(output: Path, current: dict, merged: dict) -> None:
    finance_status = ["KIỂM TRA NẠP DỮ LIỆU TÀI CHÍNH", "TikTok chỉ tách ngày khi chi tiết khớp tổng doanh thu, phí và tiền quyết toán. Xem cảnh báo đối soát bên dưới.", ""]
    for title, records in [("File tài chính vừa đọc", current.get("finance", [])), ("Tài chính trong kho lịch sử", merged.get("finance", []))]:
        finance_status.append(title + ": " + str(len(records)) + " bản ghi")
        for r in sorted(records, key=lambda r: (r.get("platform", ""), r.get("period_start", ""))):
            finance_status.append(f"{r.get('platform')} | {r.get('period_start')} → {r.get('period_end')} | {r.get('source_file', '')}")
    finance_status += ["", "Cảnh báo nhập dữ liệu:"] + list(current.get("warnings", []))
    (output / "KIEM_TRA_NAP_TAI_CHINH.txt").write_text("\n".join(finance_status), encoding="utf-8")
    ads_status = ["KIỂM TRA NẠP ADS", "File có cột Theo ngày: lấy ngày từng dòng. File không có: giữ tổng kỳ, không chia đều."]
    for r in current.get("ads", []):
        ads_status.append(f"{r.get('platform')} | {r.get('period_start')} → {r.get('period_end')} | {r.get('campaign')} | Chi phí {r.get('cost')} | {r.get('source_file')}")
    ads_status += ["", "Cảnh báo:"] + list(current.get("warnings", []))
    (output / "KIEM_TRA_NAP_ADS.txt").write_text("\n".join(ads_status), encoding="utf-8")


def write_power_bi_csv(output: Path, data: dict) -> Path:
    """CSV chuẩn hóa cho Power BI: luôn xuất từ kho lịch sử đã ghép."""
    data_out = output / "Data_Output"
    data_out.mkdir(exist_ok=True)
    write_csv(data_out / "Sales_Daily.csv", data["daily"])
    write_csv(data_out / "Overview_Period.csv", data["overview_summaries"])
    write_csv(data_out / "Source_Period.csv", flatten_source_periods(data["source_periods"]))
    write_csv(data_out / "Source_Product.csv", data["product_facts"])
    write_csv(data_out / "Content.csv", flatten_content(data["content_periods"]))
    write_csv(data_out / "Shopee_Traffic_Daily.csv", data["traffic_daily"])
    write_csv(data_out / "Ads.csv", data["ads"])
    write_csv(data_out / "Finance.csv", data["finance"])
    write_csv(data_out / "Warnings.csv", [{"warning": x} for x in data["warnings"]], ["warning"])
    return data_out


def run(input_root: Path, output: Path, baseline_dirs: list[Path] | None = None) -> int:
    output.mkdir(parents=True, exist_ok=True)
    log("=" * 68); log(f"DILIGO AUTO DASHBOARD {__version__}"); log(f"Input : {input_root}"); log(f"Output: {output}"); log("=" * 68)
    try:
        # 1) Đọc kho trước: nếu thiếu baseline khi chuyển bản thì dừng ngay, chưa làm gì.
        store, notes = load_store(output, baseline_dirs or [PROJECT_DIR, output])
        for n in notes:
            log("ℹ️ " + n)
        # 2) Đọc file mới trong Data_Input và ghép vào kho (kỳ trùng: dữ liệu mới thay dữ liệu cũ).
        current = collect_data(input_root)
        merged = merge_history_store(store["raw"], current)
        write_check_files(output, current, merged)
        preferred = preferred_report_period(current, merged)
        # 3) Xuất CSV + dashboard.
        data_out = write_power_bi_csv(output, merged)
        dashboard_data = build_dashboard_data(merged, baseline_copy(store))
        html = render_html(dashboard_data, load_automation_config(), preferred)
        (output / "index.html").write_text(html, encoding="utf-8")
        # 4) Chỉ lưu kho lịch sử sau khi toàn bộ output đã tạo thành công.
        backup = save_store(output, merged, store["baseline"])

        new_count = sum(len(current.get(k, [])) for k in ("daily", "overview_summaries", "source_periods", "content_periods", "traffic_daily", "ads", "finance"))
        log("")
        log(f"✅ XONG: {output / 'index.html'}")
        log(f"✅ Kho lịch sử: {output / HISTORY_V2_FILENAME}")
        if backup:
            log(f"✅ Bản sao kho trước lần chạy này: {backup}")
        log(f"✅ CSV cho Power BI: {data_out}")
        if preferred:
            log(f"✅ Kỳ mở mặc định: {preferred[0]} → {preferred[1]}")
        if new_count:
            log("✅ Dữ liệu mới đã được ghi vào kho lịch sử. Sau khi thấy dòng XONG này, bạn có thể xóa file raw trong Data_Input nếu muốn.")
        else:
            log("ℹ️ Data_Input không có dữ liệu mới; báo cáo được dựng lại từ kho lịch sử.")
        log(f"⚠️ Cảnh báo dữ liệu: {len(merged['warnings'])}")
        for w in merged["warnings"][:10]:
            log("   - " + w)
        return 0
    except StoreError as e:
        log("❌ " + str(e))
        return 3
    except Exception as e:
        log("❌ Script gặp lỗi:")
        log(str(e)); traceback.print_exc()
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diligo Auto Dashboard")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Thư mục Data_Input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Thư mục xuất báo cáo")
    parser.add_argument("--baseline-dir", action="append", default=None,
                        help="Thư mục chứa baseline_v25.json (chỉ cần cho lần chạy đầu tiên của bản mới)")
    args = parser.parse_args(argv)
    input_root = Path(args.input)
    if not input_root.exists():
        log(f"❌ Không tìm thấy Data_Input: {input_root}")
        log("Bạn có thể chạy: py Diligo_Auto_Dashboard.py --input D:\\Data_Input")
        return 1
    dirs = [Path(d) for d in args.baseline_dir] if args.baseline_dir else None
    return run(input_root, Path(args.output), dirs)
