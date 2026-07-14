# -*- coding: utf-8 -*-
"""
WUE.py
คำนวณประสิทธิภาพการใช้น้ำของพืชพรรณ (Water Use Efficiency: WUE)
บริเวณประเทศไทย ด้วย Google Earth Engine

นิยาม:
    WUE = GPP / ET
    - GPP (Gross Primary Production) จาก MODIS MOD17A2HGF (500 m, 8-day)
    - ET  (Evapotranspiration)      จาก MODIS MOD16A2GF  (500 m, 8-day)

หน่วยผลลัพธ์:
    GPP รวมรายปี : gC/m^2/ปี      (แปลงจาก kgC/m^2 ด้วย scale 0.0001 x 1000)
    ET  รวมรายปี : mm/ปี          (แปลงจาก kg/m^2 ด้วย scale 0.1 ; 1 kg/m^2 = 1 mm)
    WUE          : gC/m^2 ต่อ mm  = gC ต่อ kg น้ำ  (gC/kg H2O)
แล้วบันทึกเป็นแผนที่ Interactive "WUE.html"
"""

import json
import os
import ee
import geemap

PROJECT_ID = "Phasaporn-aroonjaroensuk"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML = os.path.join(BASE_DIR, "WUE.html")
THAILAND_GEOJSON = os.path.join(BASE_DIR, "Example", "Thailand_simple.geojson")

# ช่วงเวลาที่คำนวณ (ปีปฏิทิน 2024 ซึ่งข้อมูลกาปฟิลครบทั้งปี)
START_DATE = "2024-01-01"
END_DATE = "2025-01-01"

# ค่า fill value ของ MODIS (ค่าตั้งแต่ 32761 ขึ้นไปคือน้ำ/เมฆ/ไม่มีข้อมูล ต้องตัดออก)
FILL_THRESHOLD = 32761


# ---------- 1) เชื่อมต่อ Google Earth Engine ----------
def initialize_ee(project_id):
    # Cloud Project ID ต้องเป็นตัวพิมพ์เล็กเสมอ จึงลองทั้งสองแบบ
    for pid in (project_id, project_id.lower()):
        try:
            ee.Initialize(project=pid)
            print(f"เชื่อมต่อ GEE สำเร็จ (project: {pid})")
            return
        except Exception:
            pass
    # ครั้งแรกต้องยืนยันตัวตนผ่านเบราว์เซอร์ก่อน (credentials จะถูกเก็บไว้ใช้ครั้งถัดไป)
    ee.Authenticate(auth_mode="localhost")
    for pid in (project_id, project_id.lower()):
        try:
            ee.Initialize(project=pid)
            print(f"เชื่อมต่อ GEE สำเร็จ (project: {pid})")
            return
        except Exception as e:
            err = e
    raise err


initialize_ee(PROJECT_ID)

# ---------- 2) ขอบเขตประเทศไทย ----------
if os.path.exists(THAILAND_GEOJSON):
    with open(THAILAND_GEOJSON, encoding="utf-8") as f:
        roi = ee.FeatureCollection(json.load(f))
else:
    roi = (
        ee.FeatureCollection("FAO/GAUL/2015/level0")
        .filter(ee.Filter.eq("ADM0_NAME", "Thailand"))
    )


# ---------- 3) เตรียมข้อมูล GPP (MOD17A2HGF) ----------
def scale_gpp(img):
    valid = img.select("Gpp").lt(FILL_THRESHOLD)          # ตัด fill value
    gpp = (
        img.select("Gpp").updateMask(valid)
        .multiply(0.0001)   # scale factor -> kgC/m^2/8day
        .multiply(1000)     # kgC -> gC        -> gC/m^2/8day
    )
    return gpp.rename("GPP").copyProperties(img, ["system:time_start"])


gpp_coll = (
    ee.ImageCollection("MODIS/061/MOD17A2HGF")
    .filterDate(START_DATE, END_DATE)
    .filterBounds(roi)
    .map(scale_gpp)
)


# ---------- 4) เตรียมข้อมูล ET (MOD16A2GF) ----------
def scale_et(img):
    valid = img.select("ET").lt(FILL_THRESHOLD)           # ตัด fill value
    et = (
        img.select("ET").updateMask(valid)
        .multiply(0.1)      # scale factor -> mm/8day (kg/m^2 = mm)
    )
    return et.rename("ET").copyProperties(img, ["system:time_start"])


et_coll = (
    ee.ImageCollection("MODIS/061/MOD16A2GF")
    .filterDate(START_DATE, END_DATE)
    .filterBounds(roi)
    .map(scale_et)
)

n_gpp = gpp_coll.size().getInfo()
n_et = et_coll.size().getInfo()
print(f"จำนวนภาพ GPP: {n_gpp} ภาพ, ET: {n_et} ภาพ (ช่วง {START_DATE} ถึง {END_DATE})")

# ---------- 5) รวมรายปีและคำนวณ WUE ----------
gpp_annual = gpp_coll.sum().clip(roi)                     # gC/m^2/ปี
et_annual = et_coll.sum().clip(roi)                       # mm/ปี

# ป้องกันการหารด้วยศูนย์: ใช้เฉพาะจุดที่ ET รวม > 1 mm/ปี
et_annual_safe = et_annual.updateMask(et_annual.gt(1))
wue = gpp_annual.divide(et_annual_safe).rename("WUE")    # gC/m^2 ต่อ mm = gC/kg H2O

# ---------- 6) สถิติ WUE เฉลี่ยทั้งประเทศ ----------
stats = wue.reduceRegion(
    reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
    geometry=roi.geometry(),
    scale=5000,
    maxPixels=1e13,
).getInfo()
print(
    f"WUE ปี 2024 ทั้งประเทศ: เฉลี่ย {stats['WUE_mean']:.2f} gC/kg "
    f"(ต่ำสุด {stats['WUE_min']:.2f}, สูงสุด {stats['WUE_max']:.2f})"
)

# ---------- 7) กำหนดการแสดงผล ----------
vis_wue = {
    "min": 0,
    "max": 4,
    "palette": ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"],
}
vis_gpp = {
    "min": 0,
    "max": 3000,
    "palette": ["#ffffe5", "#78c679", "#238443", "#005a32"],
}
vis_et = {
    "min": 300,
    "max": 1600,
    "palette": ["#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#2b83ba"],
}

# ---------- 8) สร้างแผนที่ด้วย geemap ----------
m = geemap.Map(center=[13.5, 101.0], zoom=6)
m.add_basemap("HYBRID")  # พื้นหลัง Google Hybrid

m.addLayer(wue, vis_wue, "WUE ปี 2024 (gC/kg H2O)")
m.addLayer(gpp_annual, vis_gpp, "GPP รวมปี 2024 (gC/m2/ปี)", shown=False)
m.addLayer(et_annual, vis_et, "ET รวมปี 2024 (mm/ปี)", shown=False)
m.addLayer(
    ee.Image().paint(roi, 0, 2),
    {"palette": "red"},
    "Thailand Boundary",
)

m.add_colorbar(
    vis_wue,
    label="WUE (gC/kg H2O)",
    orientation="horizontal",
    layer_name="WUE ปี 2024 (gC/kg H2O)",
)

# ---------- 9) บันทึกเป็นไฟล์ HTML ----------
m.to_html(filename=OUTPUT_HTML, title="Water Use Efficiency - Thailand", width="100%", height="880px")
print(f"บันทึกแผนที่แล้ว: {OUTPUT_HTML}")
