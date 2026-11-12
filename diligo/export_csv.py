# -*- coding: utf-8 -*-
"""Xuất CSV chuẩn hóa cho Power BI."""
from __future__ import annotations
import csv
from pathlib import Path

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

