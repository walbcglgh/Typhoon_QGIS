import csv
import random
import urllib.request
from collections import defaultdict

from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

# 參數設定
CSV_SOURCE = "" # 下載連結或檔案路徑
TRACK_ID_FILTER = None      # None = 全部颱風；或指定單一颱風，EX: "WP092026"
LAYER_NAME = "FNV3_Ensemble_Tracks"  #圖層名稱，不必修改

COLOR_MODE = "wind_category"  # "wind_category" 即依風速等級上色；"track" 即依颱風編號上色；建議依風速等級上色

LINE_WIDTH = 0.35            # 每條系集成員路徑的線寬 (mm)
LINE_ALPHA = 160             # 透明度 0~255，數字越小越透明

SHOW_POINTS = 0              # 1 = 額外畫出每個時間點的點圖層；0 = 只畫線
POINT_SIZE = 1.2             # 點的大小 (mm)

WIND_CATEGORIES = [
    (0, 34, "#3B82F6", "Tropical Depression"),
    (34, 64, "#6FCB4F", "Tropical Storm"),
    (64, 83, "#FFC107", "Category 1"),
    (83, 96, "#FF8C00", "Category 2"),
    (96, 113, "#E5432B", "Category 3"),
    (113, 137, "#D6249F", "Category 4"),
    (137, 400, "#9B30FF", "Category 5"),
]

def read_fnv3_csv(source):
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as resp:
            text = resp.read().decode("utf-8")
        lines = text.splitlines(keepends=True)
    else:
        with open(source, "r", encoding="utf-8") as f:
            lines = f.readlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("init_time"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("找不到欄位標題列 (init_time,...)，請確認是 FNV3 的 CSV 檔")

    reader = csv.DictReader(lines[header_idx:])
    return list(reader)

def build_tracks(rows, track_id_filter=None):
    groups = defaultdict(list)
    for r in rows:
        if not r.get("lat") or not r.get("lon"):
            continue
        tid = r["track_id"]
        if track_id_filter and tid != track_id_filter:
            continue
        sample = r["sample"]
        try:
            lead_h = int(r["lead_time_hours"])
            lat = float(r["lat"])
            lon = float(r["lon"])
        except (ValueError, TypeError):
            continue
        try:
            wind = float(r.get("maximum_sustained_wind_speed_knots", ""))
        except (ValueError, TypeError):
            wind = None
        try:
            mslp = float(r.get("minimum_sea_level_pressure_hpa", ""))
        except (ValueError, TypeError):
            mslp = None

        groups[(tid, sample)].append(
            {
                "lead_h": lead_h,
                "lat": lat,
                "lon": lon,
                "valid_time": r.get("valid_time", ""),
                "mslp": mslp,
                "wind": wind,
            }
        )

    tracks = []
    for (tid, sample), pts in groups.items():
        pts.sort(key=lambda p: p["lead_h"])
        if len(pts) < 2:
            continue
        tracks.append({"track_id": tid, "sample": sample, "points": pts})
    return tracks

def build_segments(tracks):
    segments = []
    for trk in tracks:
        pts = trk["points"]
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            if p1["wind"] is not None and p2["wind"] is not None:
                wind_kt = (p1["wind"] + p2["wind"]) / 2.0
            elif p1["wind"] is not None:
                wind_kt = p1["wind"]
            else:
                wind_kt = p2["wind"]

            segments.append(
                {
                    "track_id": trk["track_id"],
                    "sample": trk["sample"],
                    "lead_h": p1["lead_h"],
                    "wind_kt": wind_kt,
                    "p1": (p1["lon"], p1["lat"]),
                    "p2": (p2["lon"], p2["lat"]),
                }
            )
    return segments

def create_track_layer(tracks):
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", LAYER_NAME, "memory")
    prov = layer.dataProvider()
    prov.addAttributes(
        [
            QgsField("track_id", QVariant.String),
            QgsField("sample", QVariant.Int),
            QgsField("n_points", QVariant.Int),
            QgsField("max_lead_h", QVariant.Int),
            QgsField("init_mslp", QVariant.Double),
        ]
    )
    layer.updateFields()

    features = []
    for trk in tracks:
        pts = [QgsPointXY(p["lon"], p["lat"]) for p in trk["points"]]
        geom = QgsGeometry.fromPolylineXY(pts)

        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        init_mslp = trk["points"][0]["mslp"]

        feat.setAttributes(
            [
                trk["track_id"],
                int(trk["sample"]),
                len(trk["points"]),
                trk["points"][-1]["lead_h"],
                init_mslp,
            ]
        )
        features.append(feat)

    prov.addFeatures(features)
    layer.updateExtents()
    return layer

def create_segment_layer(segments):
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", LAYER_NAME, "memory")
    prov = layer.dataProvider()
    prov.addAttributes(
        [
            QgsField("track_id", QVariant.String),
            QgsField("sample", QVariant.Int),
            QgsField("lead_h", QVariant.Int),
            QgsField("wind_kt", QVariant.Double),
        ]
    )
    layer.updateFields()

    features = []
    for seg in segments:
        geom = QgsGeometry.fromPolylineXY(
            [QgsPointXY(*seg["p1"]), QgsPointXY(*seg["p2"])]
        )
        feat = QgsFeature(layer.fields())
        feat.setGeometry(geom)
        feat.setAttributes(
            [seg["track_id"], int(seg["sample"]), seg["lead_h"], seg["wind_kt"]]
        )
        features.append(feat)

    prov.addFeatures(features)
    layer.updateExtents()
    return layer

def create_point_layer(tracks):
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326", LAYER_NAME + "_Points", "memory"
    )
    prov = layer.dataProvider()
    prov.addAttributes(
        [
            QgsField("track_id", QVariant.String),
            QgsField("sample", QVariant.Int),
            QgsField("lead_h", QVariant.Int),
            QgsField("valid_time", QVariant.String),
            QgsField("mslp", QVariant.Double),
            QgsField("wind_kt", QVariant.Double),
        ]
    )
    layer.updateFields()

    features = []
    for trk in tracks:
        for p in trk["points"]:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(
                QgsGeometry.fromPointXY(QgsPointXY(p["lon"], p["lat"]))
            )
            feat.setAttributes(
                [
                    trk["track_id"],
                    int(trk["sample"]),
                    p["lead_h"],
                    p["valid_time"],
                    p["mslp"],
                    p["wind"],
                ]
            )
            features.append(feat)

    prov.addFeatures(features)
    layer.updateExtents()
    return layer

def build_wind_category_ranges(symbol_factory):
    ranges = []
    for lower, upper, hexcolor, label in WIND_CATEGORIES:
        symbol = symbol_factory()
        color = QColor(hexcolor)
        color.setAlpha(LINE_ALPHA)
        symbol.setColor(color)
        ranges.append(QgsRendererRange(lower, upper, symbol, label))
    return ranges

def style_layer_by_wind_category(layer, field_name="wind_kt"):
    ranges = build_wind_category_ranges(
        lambda: QgsLineSymbol.createSimple({"width": str(LINE_WIDTH), "capstyle": "round"})
    )
    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    layer.setRenderer(renderer)
    layer.triggerRepaint()

def style_point_layer_by_wind_category(layer, field_name="wind_kt"):
    ranges = build_wind_category_ranges(
        lambda: QgsMarkerSymbol.createSimple({"size": str(POINT_SIZE)})
    )
    renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
    layer.setRenderer(renderer)
    layer.triggerRepaint()

def style_layer_by_track(layer):
    track_ids = sorted(set(f["track_id"] for f in layer.getFeatures()))
    random.seed(42)

    categories = []
    for tid in track_ids:
        color = QColor(
            random.randint(30, 220), random.randint(30, 220), random.randint(30, 220)
        )
        color.setAlpha(LINE_ALPHA)

        symbol = QgsLineSymbol.createSimple(
            {"width": str(LINE_WIDTH), "capstyle": "round"}
        )
        symbol.setColor(color)

        category = QgsRendererCategory(tid, symbol, tid)
        categories.append(category)

    renderer = QgsCategorizedSymbolRenderer("track_id", categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()

def main():
    rows = read_fnv3_csv(CSV_SOURCE)
    tracks = build_tracks(rows, TRACK_ID_FILTER)

    if not tracks:
        print("沒有找到任何可畫的路徑，請確認 CSV 內容或 TRACK_ID_FILTER 設定")
        return

    if COLOR_MODE == "wind_category":
        segments = build_segments(tracks)
        layer = create_segment_layer(segments)
        style_layer_by_wind_category(layer)
        QgsProject.instance().addMapLayer(layer)
        print(f"已加入圖層「{LAYER_NAME}」，共 {len(tracks)} 條路徑、{len(segments)} 段線段 (依風速等級上色)。")
    else:
        layer = create_track_layer(tracks)
        style_layer_by_track(layer)
        QgsProject.instance().addMapLayer(layer)
        print(f"已加入圖層「{LAYER_NAME}」，共 {len(tracks)} 條系集成員路徑 (依颱風編號上色)。")

    if SHOW_POINTS == 1:
        point_layer = create_point_layer(tracks)
        if COLOR_MODE == "wind_category":
            style_point_layer_by_wind_category(point_layer)
        QgsProject.instance().addMapLayer(point_layer)
        n_pts = sum(len(t["points"]) for t in tracks)
        print(f"已加入圖層「{LAYER_NAME}_Points」，共 {n_pts} 個時間點。")

main()
