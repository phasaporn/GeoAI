# -*- coding: utf-8 -*-
"""
Sentinel2.py
แสดงภาพดาวเทียม Sentinel-2 (Surface Reflectance) บริเวณประเทศไทย
ด้วย Google Earth Engine + geemap แล้วบันทึกเป็นแผนที่ Interactive "Sentinel2.html"
"""

import json
import os
import ee
import geemap

PROJECT_ID = "Phasaporn-aroonjaroensuk"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML = os.path.join(BASE_DIR, "Sentinel2.html")
# ใช้ขอบเขตแบบย่อ (simplified) เพราะไฟล์เต็ม 11 MB เกินขีดจำกัดคำขอของ GEE
THAILAND_GEOJSON = os.path.join(BASE_DIR, "Example", "Thailand_simple.geojson")


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


# ---------- 3) ฟังก์ชันตัดเมฆด้วยแบนด์ QA60 ----------
def mask_s2_clouds(image):
    qa = image.select("QA60")
    cloud_bit_mask = 1 << 10   # เมฆทึบ
    cirrus_bit_mask = 1 << 11  # เมฆเซอร์รัส
    mask = (
        qa.bitwiseAnd(cloud_bit_mask).eq(0)
        .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    )
    return image.updateMask(mask).divide(10000)


# ---------- 4) สร้าง Composite ภาพ Sentinel-2 ----------
s2 = (
    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(roi)
    .filterDate("2026-01-01", "2026-06-30")
    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
    .map(mask_s2_clouds)
)

composite = s2.median().clip(roi)

# ---------- 5) กำหนดการแสดงผล ----------
vis_true_color = {
    "bands": ["B4", "B3", "B2"],   # สีจริง (Red, Green, Blue)
    "min": 0.0,
    "max": 0.3,
}
vis_false_color = {
    "bands": ["B8", "B4", "B3"],   # สีผสมเท็จ เน้นพืชพรรณ (NIR, Red, Green)
    "min": 0.0,
    "max": 0.4,
}

# NDVI ดัชนีพืชพรรณ
ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
vis_ndvi = {
    "min": -0.2,
    "max": 0.8,
    "palette": ["blue", "white", "yellow", "green", "darkgreen"],
}

# ---------- 6) สร้างแผนที่ด้วย geemap ----------
m = geemap.Map(center=[13.5, 101.0], zoom=6)
m.add_basemap("HYBRID")  # พื้นหลัง Google Hybrid

m.addLayer(composite, vis_true_color, "Sentinel-2 True Color (RGB)")
m.addLayer(composite, vis_false_color, "Sentinel-2 False Color (NIR)", shown=False)
m.addLayer(ndvi, vis_ndvi, "NDVI", shown=False)
m.addLayer(
    ee.Image().paint(roi, 0, 2),
    {"palette": "red"},
    "Thailand Boundary",
)

# ---------- 7) บันทึกเป็นไฟล์ HTML ----------
m.to_html(filename=OUTPUT_HTML, title="Sentinel-2 Thailand", width="100%", height="880px")
print(f"บันทึกแผนที่แล้ว: {OUTPUT_HTML}")
