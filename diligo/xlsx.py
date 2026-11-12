# -*- coding: utf-8 -*-
"""Đọc file .xlsx bằng thư viện chuẩn (không cần openpyxl/pandas)."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Callable
from zipfile import ZipFile
import xml.etree.ElementTree as ET

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

