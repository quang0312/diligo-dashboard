# -*- coding: utf-8 -*-
"""Đọc các file xuất từ TikTok Shop Seller Center."""
from __future__ import annotations
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..utils import (
    find_header_row, iso, last_numeric_in_row, parse_date_any, parse_period_text,
    period_from_filename, row_to_dict, safe_float_dot, safe_pct, unique_headers,
)
from ..xlsx import xlsx_read_sheet
from ..taxonomy import classify_product, parse_tiktok_products

def parse_tiktok_overview(path: Path, warnings: list[str]) -> tuple[list[dict], dict|None]:
    try:
        _, rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Overview lỗi {path.name}: {e}")
        return [],None
    if not rows:
        return [],None
    ps,pe=parse_period_text(rows[0][0] if rows[0] else "")
    hi=find_header_row(rows,["gmv","đơn hàng","khách hàng"])
    if hi is None or hi+1>=len(rows):
        return [],None
    headers=unique_headers(rows[hi])
    total=row_to_dict(headers,rows[hi+1])

    def make(rec:dict,d:date,unique_ok:bool)->dict:
        gmv=safe_float_dot(rec.get("GMV"))
        live_aff=safe_float_dot(rec.get("GMV nhờ buổi LIVE của nhà sáng tạo"))
        live_seller=safe_float_dot(rec.get("GMV nhờ buổi LIVE của tài khoản kết nối"))
        video_aff=safe_float_dot(rec.get("GMV đến từ video liên kết"))
        video_seller=safe_float_dot(rec.get("GMV nhờ video của tài khoản kết nối"))
        return {
            "platform":"TikTok","date":d.isoformat(),"gmv":gmv,
            "orders":safe_float_dot(rec.get("Đơn hàng")),"sku_orders":safe_float_dot(rec.get("Đơn hàng SKU")),
            "customers":safe_float_dot(rec.get("Khách hàng")) if unique_ok else None,
            "units":safe_float_dot(rec.get("Số món bán ra")),"refund":safe_float_dot(rec.get("Hoàn tiền")),
            "cancel_gmv":None,"revenue":safe_float_dot(rec.get("Tổng doanh thu")),"page_views":safe_float_dot(rec.get("Lượt xem trang")),
            "visitors":safe_float_dot(rec.get("Khách truy cập")),"cvr":safe_float_dot(rec.get("Tỷ lệ chuyển đổi")),
            "product_impressions":safe_float_dot(rec.get("Lượt hiển thị sản phẩm")),"product_clicks":safe_float_dot(rec.get("Lượt nhấp vào sản phẩm")),
            "aov":safe_float_dot(rec.get("AOV")),"live_aff":live_aff,"live_seller":live_seller,"video_aff":video_aff,"video_seller":video_seller,
            "cancel_orders":None,"refund_orders":None,"source_file":path.name,"_mtime":path.stat().st_mtime,
        }

    daily=[]
    # Tìm header Daily có cột đầu Ngày
    daily_hi=None
    for i in range(hi+2,len(rows)):
        if rows[i] and str(rows[i][0] or "").strip().lower()=="ngày":
            daily_hi=i;break
    if daily_hi is not None:
        dh=unique_headers(rows[daily_hi])
        for r in rows[daily_hi+1:]:
            if not r or not r[0]:continue
            d=parse_date_any(r[0])
            if not d:continue
            rec=row_to_dict(dh,r)
            daily.append(make(rec,d,True if ps==pe else False))
    elif ps and ps==pe:
        daily.append(make(total,ps,True))
    if ps and pe and ps==pe and daily:
        # đảm bảo unique / refund lấy total row vì hourly có thể không có refund
        daily=[make(total,ps,True)]

    summary={
        "platform":"TikTok","period_start":iso(ps),"period_end":iso(pe),"gmv":safe_float_dot(total.get("GMV")),
        "orders":safe_float_dot(total.get("Đơn hàng")),"sku_orders":safe_float_dot(total.get("Đơn hàng SKU")),
        "customers":safe_float_dot(total.get("Khách hàng")),"cvr":safe_float_dot(total.get("Tỷ lệ chuyển đổi")),"refund":safe_float_dot(total.get("Hoàn tiền")),
        "cancel_gmv":None,"cancel_orders":None,"refund_orders":None,"source_file":path.name,"_mtime":path.stat().st_mtime,
    } if ps else None
    return daily,summary


def report_period_from_first_rows(rows:list[list[Any]], fallback_name:str)->tuple[date|None,date|None]:
    for r in rows[:5]:
        if r and r[0]:
            ps,pe=parse_period_text(r[0])
            if ps:return ps,pe
    return period_from_filename(fallback_name)


def parse_tiktok_productcard(path:Path,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok ProductCard lỗi {path.name}: {e}");return None
    ps,pe=report_period_from_first_rows(rows,path.name)
    f_ps,f_pe=period_from_filename(path.name)
    if ps and f_ps and ps!=f_ps:
        warnings.append(f"TikTok ProductCard {path.name}: tên file gợi ý {f_ps.isoformat()} nhưng nội dung là {ps.isoformat()}; hệ thống dùng ngày trong nội dung.")
    hi=find_header_row(rows,["id sản phẩm","gmv"])
    if hi is None:return None
    h=unique_headers(rows[hi]); products=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);pid=str(rec.get("ID sản phẩm") or "").strip();nm=str(rec.get("Tên sản phẩm") or "").strip()
        if not pid or not nm:continue
        brand,cat=classify_product(pid,nm,"TikTok")
        products.append({
            "platform":"TikTok","source":"Thẻ sản phẩm","period_start":iso(ps),"period_end":iso(pe),
            "product_id":pid,"product_name":nm,"brand":brand,"category":cat,
            "gmv":safe_float_dot(rec.get("GMV (₫)")),"orders":safe_float_dot(rec.get("Đơn hàng SKU")),"units":None,
            "impressions":safe_float_dot(rec.get("Lượt xem")),"clicks":safe_float_dot(rec.get("Lượt nhấp")),
            "ctr":safe_pct(rec.get("Tỷ lệ từ xem đến nhấp")),"cvr":safe_pct(rec.get("Tỷ lệ từ xem đến thanh toán")),
            "aov":None,"buyers":safe_float_dot(rec.get("Khách hàng")),"source_file":path.name,
        })
    return {"platform":"TikTok","source":"Thẻ sản phẩm","period_start":iso(ps),"period_end":iso(pe),"gmv":sum(x["gmv"] for x in products),"products":products,"source_file":path.name,"_mtime":path.stat().st_mtime}


def parse_tiktok_live(path:Path,affiliate:bool,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Live lỗi {path.name}: {e}");return None
    ps,pe=report_period_from_first_rows(rows,path.name)
    hi=find_header_row(rows,["nhà sáng tạo","gmv đến từ buổi live"])
    if hi is None:return None
    h=unique_headers(rows[hi]);items=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);creator=str(rec.get("Biệt danh") or rec.get("Nhà sáng tạo") or "").strip()
        if not creator:continue
        gmv=safe_float_dot(rec.get("GMV đến từ buổi LIVE (₫)"))
        items.append({
            "platform":"TikTok","kind":"affiliate_live" if affiliate else "live",
            "period_start":iso(ps),"period_end":iso(pe),"item_id":str(rec.get("ID nhà sáng tạo") or ""),
            "title":str(rec.get("Nhà sáng tạo") or creator),"creator":creator,"gmv":gmv,
            "orders":safe_float_dot(rec.get("Đơn hàng đã tạo")),"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào buổi LIVE")),
            "views":safe_float_dot(rec.get("Lượt xem")),"clicks":safe_float_dot(rec.get("Lượt nhấp Sản phẩm")),"source_file":path.name,
        })
    return {"platform":"TikTok","kind":"affiliate_live" if affiliate else "live","period_start":iso(ps),"period_end":iso(pe),"items":items,"_mtime":path.stat().st_mtime,"source_file":path.name}


def parse_tiktok_video(path:Path,affiliate:bool,warnings:list[str])->tuple[dict|None,list[dict]]:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Video lỗi {path.name}: {e}");return None,[]
    ps,pe=report_period_from_first_rows(rows,path.name)
    hi=find_header_row(rows,["id video","gmv đến từ video"])
    if hi is None:return None,[]
    h=unique_headers(rows[hi]);items=[];product_facts=[]
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r);vid=str(rec.get("ID video") or "").strip();creator=str(rec.get("Tên nhà sáng tạo") or "").strip()
        if not vid and not creator:continue
        gmv=safe_float_dot(rec.get("GMV đến từ video (₫)"));orders=safe_float_dot(rec.get("Đơn hàng SKU đã ghi nhận"))
        if gmv<=0 and orders<=0:continue
        products=parse_tiktok_products(rec.get("Sản phẩm"))
        cats=[];brands=[]
        for pid,nm in products:
            br,ca=classify_product(pid,nm,"TikTok");cats.append(ca);brands.append(br)
        cat="CHƯA GÁN";brand="CHƯA GÁN"
        if cats:
            uniq={x for x in cats if x!="CHƯA GÁN"}
            cat=next(iter(uniq)) if len(uniq)==1 else ("Đa ngành / chưa phân bổ" if len(uniq)>1 else "CHƯA GÁN")
            ub={x for x in brands if x!="CHƯA GÁN"}
            brand=next(iter(ub)) if len(ub)==1 else "CHƯA GÁN"
        items.append({
            "platform":"TikTok","kind":"affiliate_video" if affiliate else "video",
            "period_start":iso(ps),"period_end":iso(pe),"item_id":vid,"title":str(rec.get("Thông tin video") or vid),"creator":creator,
            "gmv":gmv,"orders":orders,"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào video")),
            "views":safe_float_dot(rec.get("VV")),"clicks":safe_float_dot(rec.get("Lượt nhấp sản phẩm")),"source_file":path.name,
        })
        source="Tiếp thị liên kết" if affiliate else "Video"
        if len(products)==1:
            pid,nm=products[0];br,ca=classify_product(pid,nm,"TikTok")
            pname=nm;pid_out=pid
        else:
            pname="Đa sản phẩm";pid_out=vid
            br,ca=brand,cat
        product_facts.append({
            "platform":"TikTok","source":source,"period_start":iso(ps),"period_end":iso(pe),
            "product_id":pid_out,"product_name":pname,"brand":br,"category":ca,
            "gmv":gmv,"orders":orders,"units":safe_float_dot(rec.get("Số món bán ra ghi nhận vào video")),
            "impressions":safe_float_dot(rec.get("Lượt hiển thị sản phẩm")),"clicks":safe_float_dot(rec.get("Lượt nhấp sản phẩm")),
            "ctr":safe_pct(rec.get("Tỷ lệ nhấp (Video)")),"cvr":safe_pct(rec.get("CTOR (đơn hàng SKU)")),"aov":None,"buyers":safe_float_dot(rec.get("Số khách hàng độc nhất")),"source_file":path.name,
        })
    return {"platform":"TikTok","kind":"affiliate_video" if affiliate else "video","period_start":iso(ps),"period_end":iso(pe),"items":items,"_mtime":path.stat().st_mtime,"source_file":path.name},product_facts


def parse_tiktok_ads(path:Path,warnings:list[str])->list[dict]:
    try: _,rows=xlsx_read_sheet(path,0)
    except Exception as e:
        warnings.append(f"TikTok Ads lỗi {path.name}: {e}");return []
    ps,pe=period_from_filename(path.name)
    hi=find_header_row(rows,["tên chiến dịch","chi phí"])
    if hi is None:
        warnings.append(f"TikTok Ads: không tìm thấy cột tên chiến dịch/chi phí: {path.name}"); return []
    if not ps or not pe:
        warnings.append(f"TikTok Ads: không xác định được kỳ trong tên file: {path.name}"); return []
    h=unique_headers(rows[hi])
    daily_mode="Theo ngày" in h
    agg:dict[tuple,dict]= {}
    seen=set()
    is_live="livestream" in path.name.lower() or path.name.lower().startswith("live campaign data")
    for r in rows[hi+1:]:
        if not r:continue
        rec=row_to_dict(h,r)
        camp=str(rec.get("Tên chiến dịch") or rec.get("Tên phiên LIVE") or "").strip()
        if not camp:continue
        day=parse_date_any(rec.get("Theo ngày")) if daily_mode else None
        if daily_mode and (not day or not ps<=day<=pe):
            warnings.append(f"TikTok Ads: ngày trống/sai/ngoài kỳ tại {path.name}; bỏ toàn bộ file để tránh thiếu số.")
            return []
        campaign_id=str(rec.get("ID chiến dịch") or camp)
        if daily_mode:
            identity=(campaign_id,iso(day))
            if identity in seen:
                warnings.append(f"TikTok Ads: trùng chiến dịch/ngày trong {path.name}; bỏ file để tránh cộng trùng.")
                return []
            seen.add(identity)
        start=end=day
        if not daily_mode: start,end=ps,pe
        cost=safe_float_dot(rec.get("Chi phí"));gmv=safe_float_dot(rec.get("Doanh thu gộp"));orders=safe_float_dot(rec.get("Số lượng đơn hàng SKU"))
        pid=str(rec.get("ID sản phẩm") or "").strip();creative=str(rec.get("Loại nội dung sáng tạo") or ("Livestream" if is_live else "Khác"))
        creator=str(rec.get("Tài khoản TikTok") or "")
        br,ca=classify_product(pid,camp,"TikTok") if pid else ("CHƯA GÁN","CHƯA GÁN")
        key=(campaign_id,creative,br,ca,iso(start),iso(end))
        if key not in agg:
            agg[key]={"platform":"TikTok","period_start":iso(start),"period_end":iso(end),"campaign_id":campaign_id,"grain":"daily" if daily_mode else "period","subtype":"TikTok Live Ads" if is_live else "TikTok Product Ads","source_mtime":path.stat().st_mtime,"campaign":camp,"creative_type":creative,"brand":br,"category":ca,"cost":0.0,"gmv":0.0,"orders":0.0,"impressions":0.0,"clicks":0.0,"source_file":path.name,"_mtime":path.stat().st_mtime}
        a=agg[key];a["cost"]+=cost;a["gmv"]+=gmv;a["orders"]+=orders
        a["impressions"]+=safe_float_dot(rec.get("Số lượt hiển thị quảng cáo sản phẩm") or rec.get("Số lượt xem phiên LIVE"))
        a["clicks"]+=safe_float_dot(rec.get("Số lượt nhấp vào quảng cáo sản phẩm"))
    return list(agg.values())


def inspect_tiktok_finance_detail(path, summary, warnings):
    """Only expose daily totals when dated detail reconciles to the report."""
    summary["daily_rows"] = []
    summary["source_mtime"] = path.stat().st_mtime
    try:
        _, rows = xlsx_read_sheet(path, "Chi tiết đơn hàng")
        headers = [str(x or "").strip() for x in rows[0]]
        labels = {"date": "Thời gian quyết toán đơn hàng", "revenue": "Tổng doanh thu",
                  "cost": "Tổng phí", "payout": "Tổng số tiền quyết toán"}
        cols = {k: headers.index(v) for k, v in labels.items()}
        totals = dict(revenue=0., cost=0., payout=0.)
        by_date = {}; count = 0; valid = True
        start, end = parse_date_any(summary["period_start"]), parse_date_any(summary["period_end"])
        for row in rows[1:]:
            if not any(x not in (None, "") for x in row):
                continue
            count += 1
            dt = parse_date_any(row[cols["date"]] if cols["date"] < len(row) else None)
            if not dt or not start <= dt <= end:
                valid = False
                continue
            values = {}
            for key in ("revenue", "cost", "payout"):
                cell = row[cols[key]] if cols[key] < len(row) else None
                try:
                    values[key] = float(str(cell).strip())
                    if not math.isfinite(values[key]): valid = False
                except (ValueError, TypeError):
                    valid = False
                    values[key] = 0.
            day = by_date.setdefault(iso(dt), dict(revenue=0., cost=0., payout=0.))
            for key, val in values.items():
                totals[key] += val
                day[key] += val
        summary["detail_count"] = count
        summary["detail_payout"] = totals["payout"]
        reconciled = valid and count > 0 and totals["cost"] <= 0 and abs(abs(totals["payout"]-totals["revenue"]-totals["cost"])-summary["adjustment"]) <= 1 and all(abs((abs(totals[k]) if k == "cost" else totals[k]) - summary[k]) <= 1 for k in totals)
        summary["detail_status"] = "reconciled" if reconciled else "incomplete"
        if not reconciled:
            summary["detail_note"] = f"Chi tiết có {count} giao dịch, tổng quyết toán {totals['payout']:,.0f}đ; tổng báo cáo {summary['payout']:,.0f}đ. Chưa đối soát đủ để tách ngày."
            warnings.append(f"TikTok Finance {path.name}: " + summary["detail_note"])
            return summary
        # Reconciled report covers every date in its declared range, including zero-activity days.
        dt = start
        while dt <= end:
            v = by_date.get(iso(dt), dict(revenue=0., cost=0., payout=0.))
            summary["daily_rows"].append({"platform": "TikTok", "period_start": iso(dt), "period_end": iso(dt),
                "revenue": v["revenue"], "cost": -v["cost"],
                "adjustment": v["payout"]-v["revenue"]-v["cost"], "payout": v["payout"],
                "source_file": path.name, "note": "Theo ngày quyết toán; chi tiết đã khớp tổng kỳ"})
            dt += timedelta(days=1)
        summary["detail_note"] = "Chi tiết theo ngày quyết toán đã khớp doanh thu, phí và tiền quyết toán tổng kỳ. Điều chỉnh theo ngày giữ dấu."
    except Exception as exc:
        summary["detail_status"] = "unavailable"
        summary["detail_note"] = "Chưa đọc được chi tiết theo ngày quyết toán: " + str(exc)
        warnings.append(f"TikTok Finance {path.name}: " + summary["detail_note"])
    return summary


def parse_tiktok_finance(path:Path,warnings:list[str])->dict|None:
    try: _,rows=xlsx_read_sheet(path,"Báo cáo")
    except Exception as e:
        warnings.append(f"TikTok Finance lỗi {path.name}: {e}");return None
    ps=pe=None;vals={}
    wanted={"Tổng số tiền quyết toán":"payout","Tổng doanh thu":"revenue","Tổng phí":"cost","Điều chỉnh":"adjustment",
            "Phí giao dịch":"transaction_fee","Phí hoa hồng của TikTok Shop":"commission_fee","Phí vận chuyển của người bán":"shipping_fee",
            "Hoa hồng liên kết":"affiliate_fee","Hoa hồng liên kết Quảng cáo cửa hàng":"affiliate_ads_fee","Phí dịch vụ Voucher Xtra":"voucher_fee","Phí xử lý đơn hàng":"processing_fee",
            "GMV thanh toán cho Quảng cáo TikTok":"ads_adjustment"}
    for r in rows:
        cells=[str(x).strip() if x not in (None,"") else "" for x in r]
        if "Khoảng thời gian" in cells:
            txt=next((x for x in cells if "20" in x and "/" in x),"");ps,pe=parse_period_text(txt)
        for lab,key in wanted.items():
            if lab in cells:
                vals[key]=last_numeric_in_row(r)
    if not ps:ps,pe=period_from_filename(path.name)
    if not ps or not pe:
        warnings.append(f"TikTok Finance: không xác định được kỳ của {path.name}")
        return None
    result = {"platform":"TikTok","period_start":iso(ps),"period_end":iso(pe),"revenue":vals.get("revenue",0),"cost":abs(vals.get("cost",0)),"adjustment":abs(vals.get("adjustment",0)),"payout":vals.get("payout",0),"transaction_fee":abs(vals.get("transaction_fee",0)),"commission_fee":abs(vals.get("commission_fee",0)),"shipping_fee":abs(vals.get("shipping_fee",0)),"affiliate_fee":abs(vals.get("affiliate_fee",0)),"affiliate_ads_fee":abs(vals.get("affiliate_ads_fee",0)),"voucher_fee":abs(vals.get("voucher_fee",0)),"processing_fee":abs(vals.get("processing_fee",0)),"ads_adjustment":abs(vals.get("ads_adjustment",0)),"source_file":path.name,"_mtime":path.stat().st_mtime}
    return inspect_tiktok_finance_detail(path, result, warnings)


