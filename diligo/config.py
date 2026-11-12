# -*- coding: utf-8 -*-
"""Cấu hình cố định: đường dẫn mặc định, tên file kho lịch sử, bảng gán nhãn/ngành."""
from __future__ import annotations
from pathlib import Path

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

# Từ bản 40: kho lịch sử gộp (raw + baseline) trong một file.
HISTORY_V2_FILENAME = "HistoryStore_v2.json"
BASELINE_FILENAME = "baseline_v25.json"
BACKUP_DIRNAME = "HistoryStore_backups"
BACKUP_KEEP = 10
