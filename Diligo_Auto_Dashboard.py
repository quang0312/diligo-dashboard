# -*- coding: utf-8 -*-
r"""DILIGO AUTO DASHBOARD

    D:\Data_Input  -> chạy script -> D:\Diligo_Dashboard_Output\index.html

Chạy bằng CAP_NHAT_BAO_CAO.bat hoặc:
    py Diligo_Auto_Dashboard.py --input D:\Data_Input --output D:\Diligo_Dashboard_Output

Code nằm trong thư mục diligo/ (xem README.md).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diligo.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
