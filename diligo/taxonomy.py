# -*- coding: utf-8 -*-
"""Gán nhãn hàng / ngành hàng cho sản phẩm."""
from __future__ import annotations
import re
from typing import Any

from .config import SHOPEE_MIXED_OVERRIDES, TIKTOK_MIXED_OVERRIDES

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
