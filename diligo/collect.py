# -*- coding: utf-8 -*-
"""Quét thư mục Data_Input, gọi đúng bộ đọc cho từng loại file và khử trùng kỳ."""
from __future__ import annotations
from pathlib import Path

from .utils import dedup_by_period
from .parsers.shopee import (
    SHOPEE_SOURCE_FILES, parse_shopee_ads_file, parse_shopee_contribution, parse_shopee_finance,
    parse_shopee_overview, parse_shopee_source, parse_shopee_traffic_daily,
)
from .parsers.tiktok import (
    parse_tiktok_ads, parse_tiktok_finance, parse_tiktok_live, parse_tiktok_overview,
    parse_tiktok_productcard, parse_tiktok_video,
)
from .store import _ads_family

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



