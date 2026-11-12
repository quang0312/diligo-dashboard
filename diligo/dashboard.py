# -*- coding: utf-8 -*-
"""Dựng dữ liệu + file HTML dashboard từ kho lịch sử.

Trước bản 40 phần này gọi là "V25 compatibility layer" và tự đọc baseline_v25.json
mỗi lần chạy. Nay baseline nằm trong HistoryStore_v2.json và được truyền vào.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_FILE = PROJECT_DIR / "templates" / "dashboard.html"
CONFIG_FILE = PROJECT_DIR / "AUTOMATION_CONFIG.json"
STATE_PLACEHOLDER = "const state={platform:'All',source:'Overall',brand:'All',category:null,from:'2026-09-01',to:'2026-09-16',page:'overview'};"


def _v25_source_name(platform: str, source: str) -> str:
    if platform == "Shopee":
        return {"Thẻ sản phẩm":"Product Card","Phát trực tiếp":"Live","Video":"Video","Tiếp thị liên kết":"Affiliate"}.get(source, source)
    return {"Thẻ sản phẩm":"Product Card","Phát trực tiếp":"Live Official","Video":"Video Official","Tiếp thị liên kết":"Video Affiliate"}.get(source, source)


def _merge_by_key(old: list[dict], new: list[dict], key_fn):
    m = {key_fn(r): r for r in old}
    for r in new:
        m[key_fn(r)] = r
    return list(m.values())


def _v25_categories_products(raw: dict) -> tuple[list[dict], list[dict]]:
    facts = raw.get("product_facts", [])
    groups: dict[tuple, dict] = {}
    product_groups: dict[tuple, dict] = {}
    for x in facts:
        p=x.get("platform") or ""
        src=_v25_source_name(p, x.get("source") or "")
        a=x.get("period_start") or ""; b=x.get("period_end") or a
        brand=x.get("brand") or "CHƯA GÁN"; cat=x.get("category") or "CHƯA GÁN"
        k=(p,src,a,b,brand,cat)
        g=groups.setdefault(k,{"platform":p,"source":src,"start":a,"end":b,"brand":brand,"category":cat,"gmv":0.0,"orders":0.0,"units":0.0,"quality":"Exact product-level · auto","usable":True,"coverage":1.0})
        g["gmv"] += float(x.get("gmv") or 0); g["orders"] += float(x.get("orders") or 0); g["units"] += float(x.get("units") or 0)
        pk=(p,src,a,b,brand,cat,str(x.get("product_id") or ""),x.get("product_name") or "")
        q=product_groups.setdefault(pk,{"platform":p,"source":src,"start":a,"end":b,"brand":brand,"category":cat,"pid":str(x.get("product_id") or ""),"name":x.get("product_name") or "","gmv":0.0,"orders":0.0,"units":0.0,"impressions":0.0,"clicks":0.0,"quality":"Exact product-level · auto","coverage":1.0})
        q["gmv"] += float(x.get("gmv") or 0); q["orders"] += float(x.get("orders") or 0); q["units"] += float(x.get("units") or 0); q["impressions"] += float(x.get("impressions") or 0); q["clicks"] += float(x.get("clicks") or 0)
    cats=list(groups.values())
    # share/rank inside exact platform/source/period
    buckets={}
    for r in cats:buckets.setdefault((r["platform"],r["source"],r["start"],r["end"]),[]).append(r)
    for rr in buckets.values():
        rr.sort(key=lambda z:z["gmv"],reverse=True); tot=sum(z["gmv"] for z in rr) or 1
        for i,z in enumerate(rr,1):z["share"]=z["gmv"]/tot;z["rank"]=i
    prods=list(product_groups.values())
    pb={}
    for r in prods:pb.setdefault((r["platform"],r["source"],r["start"],r["end"],r["brand"],r["category"]),[]).append(r)
    for rr in pb.values():
        rr.sort(key=lambda z:z["gmv"],reverse=True);tot=sum(z["gmv"] for z in rr) or 1
        for i,z in enumerate(rr,1):
            z["share_cat"]=z["gmv"]/tot;z["rank"]=i
            z["ctr"]=(z.get("clicks") or 0)/(z.get("impressions") or 1) if z.get("impressions") else None
            z["cvr"]=(z.get("orders") or 0)/(z.get("clicks") or 1) if z.get("clicks") else None
            z["aov"]=(z.get("gmv") or 0)/(z.get("orders") or 1) if z.get("orders") else None
    return cats,prods


def _v25_content(raw: dict) -> dict[str,list[dict]]:
    out={"top_videos_shopee":[],"top_live_shopee":[],"top_videos_tiktok_official":[],"top_live_tiktok_official":[],"top_creators_tiktok_affiliate":[],"top_creators_shopee_affiliate":[]}
    # records are period-scoped; keep period fields so HTML date filter can select them.
    for p in raw.get("content_periods",[]):
        a=p.get("period_start");b=p.get("period_end") or a;plat=p.get("platform");kind=p.get("kind")
        items=p.get("items",[])
        if plat=="Shopee" and kind=="video":
            total=sum(float(x.get("gmv") or 0) for x in items) or 1
            for x in items:
                out["top_videos_shopee"].append({"start":a,"end":b,"video_id":x.get("item_id"),"video":x.get("title"),"share":float(x.get("gmv") or 0)/total,"gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"cvr":0})
        elif plat=="Shopee" and kind=="live":
            for x in items:
                out["top_live_shopee"].append({"start":a,"end":b,"session_id":x.get("item_id"),"session":x.get("title"),"gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0)})
        elif plat=="TikTok" and kind=="video":
            for x in items:
                out["top_videos_tiktok_official"].append({"start":a,"end":b,"creator":x.get("creator"),"video_id":x.get("item_id"),"video_info":x.get("title"),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"orders":float(x.get("orders") or 0),"gmv":float(x.get("gmv") or 0)})
        elif plat=="TikTok" and kind=="live":
            for x in items:
                out["top_live_tiktok_official"].append({"start":a,"end":b,"creator":x.get("creator"),"session_id":x.get("item_id"),"session":x.get("title"),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0),"orders":float(x.get("orders") or 0),"units":float(x.get("units") or 0),"gmv":float(x.get("gmv") or 0)})
        elif plat=="TikTok" and kind in {"affiliate_video","affiliate_live"}:
            for x in items:
                nm=x.get("creator") or x.get("title") or x.get("item_id")
                out["top_creators_tiktok_affiliate"].append({"start":a,"end":b,"creator_id":nm,"name":nm,"nickname":"","total_gmv":float(x.get("gmv") or 0),"video_gmv":float(x.get("gmv") or 0) if kind=="affiliate_video" else 0.0,"live_gmv":float(x.get("gmv") or 0) if kind=="affiliate_live" else 0.0,"orders":float(x.get("orders") or 0),"videos":1 if kind=="affiliate_video" else 0,"live_sessions":1 if kind=="affiliate_live" else 0,"clicks":float(x.get("clicks") or 0),"views":float(x.get("views") or 0)})
        elif plat=="Shopee" and kind in {"affiliate","affiliate_video","affiliate_live"}:
            for x in items:
                nm=x.get("creator") or x.get("title") or x.get("item_id")
                # Keep only rows that actually have attributed GMV/orders for ranking.
                if float(x.get("gmv") or 0)<=0 and float(x.get("orders") or 0)<=0: continue
                channel = x.get("affiliate_channel") or ("Video" if kind=="affiliate_video" else "Live" if kind=="affiliate_live" else None)
                out["top_creators_shopee_affiliate"].append({"start":a,"end":b,"creator_id":nm,"name":nm,"channel":channel,"total_gmv":float(x.get("gmv") or 0),"orders":float(x.get("orders") or 0),"views":float(x.get("views") or 0),"clicks":float(x.get("clicks") or 0)})
    return out


def build_dashboard_data(raw: dict, baseline: dict) -> dict:
    """Ghép dữ liệu nền (baseline) với kho raw thành dữ liệu cho dashboard.
    Quy tắc: cùng khóa (sàn/kỳ/...) thì dữ liệu raw thắng. `baseline` bị sửa tại chỗ,
    hãy truyền vào một bản sao (store.baseline_copy)."""
    base=baseline
    # Daily: raw file for a date wins over historical embedded record.
    base["daily"]=_merge_by_key(base.get("daily",[]),raw.get("daily",[]),lambda r:(r.get("platform"),r.get("date")))
    base["daily"].sort(key=lambda r:(r.get("date") or "",r.get("platform") or ""))

    # Exact Overview period summaries are useful for week/month comparison (especially CVR/unique metrics).
    # Raw/history wins for the same platform + exact period.
    overview_fresh=[]
    for r in raw.get("overview_summaries",[]):
        overview_fresh.append({
            "platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),
            "gmv":float(r.get("gmv") or 0),"orders":float(r.get("orders") or 0),
            "sku_orders":float(r.get("sku_orders") or 0),"customers":r.get("customers"),
            "cvr":r.get("cvr"),"refund":float(r.get("refund") or 0),
            "cancel_gmv":r.get("cancel_gmv"),"cancel_orders":r.get("cancel_orders"),
            "refund_orders":r.get("refund_orders"),"source_file":r.get("source_file")
        })
    base["overview_periods"]=_merge_by_key(base.get("overview_periods",[]),overview_fresh,lambda r:(r.get("platform"),r.get("period_start"),r.get("period_end")))

    # Source periods: only Shopee needs period-aware source table; raw wins same period/source.
    fresh=[]
    for r in raw.get("source_periods",[]):
        if r.get("platform")!="Shopee": continue
        fresh.append({"platform":"Shopee","source":_v25_source_name("Shopee",r.get("source") or ""),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"gmv":float(r.get("gmv") or 0),"orders":r.get("orders"),"units":r.get("units"),"quality":"Auto từ file raw"})
    base["source_periods"]=_merge_by_key(base.get("source_periods",[]),fresh,lambda r:(r.get("platform"),r.get("source"),r.get("period_start"),r.get("period_end")))

    cats,prods=_v25_categories_products(raw)
    base["categories"]=_merge_by_key(base.get("categories",[]),cats,lambda r:(r.get("platform"),r.get("source"),r.get("start"),r.get("end"),r.get("brand"),r.get("category")))
    base["products"]=_merge_by_key(base.get("products",[]),prods,lambda r:(r.get("platform"),r.get("source"),r.get("start"),r.get("end"),r.get("brand"),r.get("category"),str(r.get("pid") or ""),r.get("name")))

    ct=_v25_content(raw)
    for key,arr in ct.items():
        old=base.get(key,[])
        # Replace whole same platform-kind periods implicitly by period+item id/name.
        if key=="top_videos_shopee": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("video_id") or ""))
        elif key=="top_live_shopee": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("session_id") or ""))
        elif key=="top_videos_tiktok_official": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("video_id") or ""))
        elif key=="top_live_tiktok_official": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("session_id") or r.get("creator") or ""))
        elif key=="top_creators_shopee_affiliate": kf=lambda r:(r.get("start"),r.get("end"),str(r.get("creator_id") or r.get("name") or ""),r.get("channel"))
        else: kf=lambda r:(r.get("start"),r.get("end"),str(r.get("creator_id") or r.get("name") or ""))
        base[key]=_merge_by_key(old,arr,kf)

    # Ads periods. Remove same platform/period raw groups then append raw detail; this prevents baseline day15 summary + raw detail double count.
    raw_ads=raw.get("ads",[])
    if raw_ads:
        periods={(r.get("platform"),r.get("period_start"),r.get("period_end")) for r in raw_ads}
        keep=[r for r in base.get("ads_periods",[]) if (r.get("platform"),r.get("period_start"),r.get("period_end")) not in periods]
        for r in raw_ads:
            rr={"platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"subtype":r.get("subtype") or "Ads","campaign":r.get("campaign") or r.get("subtype") or "Ads","cost":float(r.get("cost") or 0),"gmv":float(r.get("gmv") or 0),"orders":r.get("orders"),"headline":bool(r.get("headline")),"note":"Auto từ file raw", **{k:r[k] for k in ("daily_rows","detail_status","detail_note","detail_count","detail_payout","source_file","source_mtime","grain","campaign_id") if k in r}}
            keep.append(rr)
        base["ads_periods"]=keep

    # Shopee internal traffic sources at daily grain; raw/history wins by date + source.
    base["shopee_traffic_daily"]=_merge_by_key(
        base.get("shopee_traffic_daily",[]), raw.get("traffic_daily",[]),
        lambda r:(r.get("date"),r.get("main_source"),r.get("traffic_source"))
    )
    _traffic_allowed = {
        "Product Card": {"Thẻ sản phẩm","Tìm kiếm","Đề xuất","Cửa hàng","Đơn mua của tôi","Giỏ hàng","Khuyến mãi","Chat","Khác"},
        "Live": {"Live","Cửa hàng","Giỏ hàng","Đề xuất","Tìm kiếm","Đơn mua của tôi","Video","Thẻ Live","Trang chủ Shopee Live","Chat","Khác"},
        "Video": {"Video","Tìm kiếm","Đề xuất","Cửa hàng","Giỏ hàng","Đơn mua của tôi","Thẻ Video","Video nổi bật","Trang chủ Shopee Video","Chat","Hồ sơ người tạo","Khác"},
        "Affiliate": {"Tiếp thị liên kết","Affiliate Video","Affiliate Live","Khác"},
    }
    base["shopee_traffic_daily"]=[r for r in base["shopee_traffic_daily"] if r.get("traffic_source") in _traffic_allowed.get(r.get("main_source"), set())]
    base["shopee_traffic_daily"].sort(key=lambda r:(r.get("date") or "",r.get("main_source") or "",r.get("traffic_source") or ""))

    raw_fin=raw.get("finance",[])
    if raw_fin:
        periods={(r.get("platform"),r.get("period_start"),r.get("period_end")) for r in raw_fin}
        keep=[r for r in base.get("finance_periods",[]) if (r.get("platform"),r.get("period_start"),r.get("period_end")) not in periods]
        for r in raw_fin:
            keep.append({"platform":r.get("platform"),"period_start":r.get("period_start"),"period_end":r.get("period_end"),"revenue":float(r.get("revenue") or 0),"cost":abs(float(r.get("cost") or 0)),"adjustment":abs(float(r.get("adjustment") or 0)),"payout":float(r.get("payout") or 0),"note":"Auto từ file raw", **{k:r[k] for k in ("daily_rows","detail_status","detail_note","detail_count","detail_payout","source_file","source_mtime","grain","campaign_id") if k in r}})
        base["finance_periods"]=keep
    base["warnings"]=raw.get("warnings",[])
    return base


def load_automation_config(config_path: Path = CONFIG_FILE) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config.get("owners"), dict) or not isinstance(config.get("deadlines"), dict) or not 0 < float(config.get("peak_share", 0)) <= 1:
        raise ValueError("AUTOMATION_CONFIG.json: kiểm tra owners, deadlines và peak_share (0–1)")
    return config


def render_html(data: dict, config: dict, preferred_period: tuple[str,str] | None = None,
                template_path: Path = TEMPLATE_FILE) -> str:
    template=template_path.read_text(encoding="utf-8")
    if STATE_PLACEHOLDER not in template or "__DATA__" not in template or "__AUTO_CONFIG__" not in template:
        raise ValueError(f"Template {template_path} thiếu chỗ chèn dữ liệu (__DATA__/__AUTO_CONFIG__/state).")
    txt=template.replace("__DATA__",json.dumps(data,ensure_ascii=False,separators=(",",":")))
    txt = txt.replace("__AUTO_CONFIG__", json.dumps(config, ensure_ascii=False).replace("<", "\\u003c"))
    dates=sorted({r.get("date") for r in data.get("daily",[]) if r.get("date")})
    if dates:
        if preferred_period:
            mn,mx=preferred_period
        else:
            mx=dates[-1]
            latest_month=mx[:7]
            same_month=[d for d in dates if d.startswith(latest_month)]
            mn=same_month[0] if same_month else mx
        txt=txt.replace(STATE_PLACEHOLDER,f"const state={{platform:'All',source:'Overall',brand:'All',category:null,from:'{mn}',to:'{mx}',page:'overview'}};")
    return txt
