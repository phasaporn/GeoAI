# -*- coding: utf-8 -*-
"""
ET_MOD16.py
คำนวณค่าคายระเหยน้ำ (Evapotranspiration: ET) จากผลิตภัณฑ์ MODIS MOD16A2GF
(Terra Net Evapotranspiration 8-Day, 500 m) ด้วย Google Earth Engine
บริเวณประเทศไทย แล้วบันทึกเป็นแผนที่ Interactive "ET_MOD16.html"

หมายเหตุหน่วยข้อมูล:
- แบนด์ ET เก็บเป็น kg/m^2/8day โดยมี scale factor 0.1
- 1 kg/m^2 ของน้ำ = ความลึกน้ำ 1 มิลลิเมตร ดังนั้น ET ที่คูณ 0.1 แล้วมีหน่วยเป็น mm
"""

import json
import os
import ee
import geemap

PROJECT_ID = "Phasaporn-aroonjaroensuk"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML = os.path.join(BASE_DIR, "ET_MOD16.html")
THAILAND_GEOJSON = os.path.join(BASE_DIR, "Example", "Thailand_simple.geojson")

# ช่วงเวลาที่คำนวณ (ปีปฏิทิน 2024 ซึ่งข้อมูล MOD16A2GF ครบทั้งปี)
START_DATE = "2024-01-01"
END_DATE = "2025-01-01"


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

# ---------- 3) โหลดข้อมูล MOD16A2GF และแปลงหน่วย ----------
mod16 = (
    ee.ImageCollection("MODIS/061/MOD16A2GF")
    .filterDate(START_DATE, END_DATE)
    .filterBounds(roi)
    .select("ET")
    # scale factor 0.1 -> หน่วยเป็น mm/8day
    .map(lambda img: img.multiply(0.1).copyProperties(img, ["system:time_start"]))
)

count = mod16.size().getInfo()
print(f"จำนวนภาพ MOD16A2GF ในช่วง {START_DATE} ถึง {END_DATE}: {count} ภาพ")

# ---------- 4) คำนวณ ET ----------
# ET รวมทั้งปี (mm/year) = ผลรวมของทุกช่วง 8 วัน
et_annual = ee.ImageCollection(mod16).sum().clip(roi)

# ET เฉลี่ยต่อช่วง 8 วัน (mm/8day)
et_mean_8day = ee.ImageCollection(mod16).mean().clip(roi)

# ---------- 5) สถิติ ET เฉลี่ยทั้งประเทศ ----------
stats = et_annual.reduceRegion(
    reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
    geometry=roi.geometry(),
    scale=5000,
    maxPixels=1e13,
).getInfo()
print(
    f"ET รวมปี 2024 ทั้งประเทศ: เฉลี่ย {stats['ET_mean']:.1f} mm/ปี "
    f"(ต่ำสุด {stats['ET_min']:.1f}, สูงสุด {stats['ET_max']:.1f})"
)

# ---------- 6) กำหนดการแสดงผล ----------
vis_annual = {
    "min": 300,
    "max": 1600,
    "palette": [
        "#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#2b83ba",
    ],  # แดง (ET ต่ำ) -> น้ำเงิน (ET สูง)
}
vis_8day = {
    "min": 0,
    "max": 40,
    "palette": ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"],
}

# ---------- 7) สร้างแผนที่ด้วย geemap ----------
m = geemap.Map(center=[13.5, 101.0], zoom=6)
m.add_basemap("HYBRID")  # พื้นหลัง Google Hybrid

m.addLayer(et_annual, vis_annual, "ET รวมปี 2024 (mm/year)")
m.addLayer(et_mean_8day, vis_8day, "ET เฉลี่ยรอบ 8 วัน (mm/8day)", shown=False)
m.addLayer(
    ee.Image().paint(roi, 0, 2),
    {"palette": "red"},
    "Thailand Boundary",
)

m.add_colorbar(
    vis_annual,
    label="ET (mm/year)",
    orientation="horizontal",
    layer_name="ET รวมปี 2024 (mm/year)",
)

# ---------- 8) บันทึกเป็นไฟล์ HTML ----------
m.to_html(filename=OUTPUT_HTML, title="MOD16 Evapotranspiration - Thailand", width="100%", height="880px")
print(f"บันทึกแผนที่แล้ว: {OUTPUT_HTML}")
