import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
    QgsFields,
    QgsMarkerSymbol,
    QgsSimpleMarkerSymbolLayer,
    QgsLineSymbol,
    QgsFillSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

API_KEY = ""
RESOURCE_ID = "W-C0034-005"
API_URL = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{RESOURCE_ID}?Authorization={API_KEY}"

USE_LOCAL_FILE = False
LOCAL_JSON_PATH = "/path/to/your/typhoon.json"

ALL_TYPHOONS = True
TARGET_TYPHOON_NO = None
TARGET_TYPHOON_NAME = None

DRAW_RADIUS_15MS = True
DRAW_RADIUS_25MS = True
RADIUS_CIRCLE_SEGMENTS = 64

INTENSITY_CATEGORIES = [
    (0.0,   17.2,  "TD",        "熱帶性低氣壓", "120,166,156,255"),
    (17.2,  32.7,  "TY_LIGHT",  "輕度颱風",     "233,196,84,255"),
    (32.7,  51.0,  "TY_MID",    "中度颱風",     "224,135,62,255"),
    (51.0,  999.0, "TY_STRONG", "強烈颱風",     "178,58,52,255"),
]

LABEL_BOX_MARGIN_RATIO    = 0.15
LABEL_ANGLE_STEP_DEG      = 18
LABEL_PREFERRED_ANGLE_DEG = 55
LABEL_BOX_ASPECT          = (1.9, 0.55)

EARTH_RADIUS_KM = 6371.0088


def classify_intensity(max_wind_speed):
    try:
        w = float(max_wind_speed)
    except (TypeError, ValueError):
        return ("UNKNOWN", "未知", "180,180,180,255")
    for lo, hi, code, label, color in INTENSITY_CATEGORIES:
        if lo <= w < hi:
            return (code, label, color)
    return ("TY_STRONG", "強烈颱風", "220,20,20,255")


def fetch_typhoon_json():
    if USE_LOCAL_FILE:
        with open(LOCAL_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(f"無法連線到 CWA API: {e}")


def pick_typhoons(data):
    cyclones = data["records"]["TropicalCyclones"]["TropicalCyclone"]
    if not isinstance(cyclones, list):
        cyclones = [cyclones]
    if ALL_TYPHOONS:
        return cyclones
    if TARGET_TYPHOON_NO is not None:
        matched = [c for c in cyclones
                   if c.get("CwaTyNo") == TARGET_TYPHOON_NO or c.get("CwaTdNo") == TARGET_TYPHOON_NO]
        if not matched:
            raise ValueError(f"找不到編號為 {TARGET_TYPHOON_NO} 的颱風")
        return matched
    if TARGET_TYPHOON_NAME is not None:
        matched = [c for c in cyclones
                   if c.get("TyphoonName", "").upper() == TARGET_TYPHOON_NAME.upper()]
        if not matched:
            raise ValueError(f"找不到名稱為 {TARGET_TYPHOON_NAME} 的颱風")
        return matched
    return cyclones[:1]


def get_circle(fix, key):
    c = fix.get(key)
    if not c:
        return None
    return c


def get_moving_prediction_zh(fix):
    mp = fix.get("MovingPrediction")
    if not mp:
        return ""
    for item in mp:
        if item.get("lang") == "zh-hant":
            return item.get("value", "")
    return mp[0].get("value", "") if mp else ""


def format_time_label(dt_str, forecast_hr=""):
    try:
        clean = dt_str or ""
        if clean.endswith("Z"):
            clean = clean[:-1]
        elif len(clean) > 6 and clean[-6] in ("+", "-") and clean[-3] == ":":
            clean = clean[:-6]
        dt = datetime.fromisoformat(clean)
        if forecast_hr:
            dt = dt + timedelta(hours=int(forecast_hr))
        return dt.strftime("%m/%d %H:%M")
    except (ValueError, TypeError):
        return dt_str or "?"


def make_geo_circle(center_lon, center_lat, radius_km, segments=RADIUS_CIRCLE_SEGMENTS):
    if radius_km is None or radius_km <= 0:
        return None
    lat_rad = math.radians(center_lat)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * max(math.cos(lat_rad), 0.01)
    points = []
    for i in range(segments + 1):
        theta = 2.0 * math.pi * i / segments
        dlon = (radius_km * math.cos(theta)) / km_per_deg_lon
        dlat = (radius_km * math.sin(theta)) / km_per_deg_lat
        points.append(QgsPointXY(center_lon + dlon, center_lat + dlat))
    return points


def _km_per_degree(lat):
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * max(math.cos(math.radians(lat)), 0.01)
    return km_per_deg_lat, km_per_deg_lon


def estimate_leader_length_km(points):
    if len(points) < 2:
        return 40.0

    def haversine_km(lon1, lat1, lon2, lat2):
        R = 6371.0088
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    dists = []
    for i in range(len(points) - 1):
        lon1, lat1, _ = points[i]
        lon2, lat2, _ = points[i + 1]
        d = haversine_km(lon1, lat1, lon2, lat2)
        if d > 0:
            dists.append(d)
    if not dists:
        return 40.0
    dists.sort()
    return max(dists[len(dists) // 2] * 0.35, 8.0)


def _label_box_for_angle(lon, lat, angle_deg, leader_km, w_km, h_km):
    km_per_deg_lat, km_per_deg_lon = _km_per_degree(lat)
    rad = math.radians(angle_deg)
    end_dlon = (leader_km * math.cos(rad)) / km_per_deg_lon
    end_dlat = (leader_km * math.sin(rad)) / km_per_deg_lat
    label_lon = lon + end_dlon
    label_lat = lat + end_dlat
    box_cx_lon = label_lon + (w_km / 2 * math.cos(rad)) / km_per_deg_lon
    box_cy_lat = label_lat + (h_km / 2 * math.sin(rad)) / km_per_deg_lat
    half_w_deg = (w_km / 2) / km_per_deg_lon
    half_h_deg = (h_km / 2) / km_per_deg_lat
    west  = box_cx_lon - half_w_deg
    east  = box_cx_lon + half_w_deg
    south = box_cy_lat - half_h_deg
    north = box_cy_lat + half_h_deg
    return (west, east, south, north), (label_lon, label_lat)


def _boxes_overlap(box1, box2, margin_deg_lon=0.0, margin_deg_lat=0.0):
    w1, e1, s1, n1 = box1
    w2, e2, s2, n2 = box2
    if e1 + margin_deg_lon < w2 or e2 + margin_deg_lon < w1:
        return False
    if n1 + margin_deg_lat < s2 or n2 + margin_deg_lat < s1:
        return False
    return True


def assign_leader_line_angles(points):
    if not points:
        return []
    leader_km = estimate_leader_length_km(points)
    w_km      = leader_km * LABEL_BOX_ASPECT[0]
    h_km      = leader_km * LABEL_BOX_ASPECT[1]
    margin_km = leader_km * LABEL_BOX_MARGIN_RATIO
    placed_boxes = []
    results = []
    n_candidates = max(1, int(360 / LABEL_ANGLE_STEP_DEG))

    for lon, lat, point_id in points:
        km_per_deg_lat, km_per_deg_lon = _km_per_degree(lat)
        margin_deg_lon = margin_km / km_per_deg_lon
        margin_deg_lat = margin_km / km_per_deg_lat

        candidates = [LABEL_PREFERRED_ANGLE_DEG]
        for step in range(1, n_candidates + 1):
            candidates.append(LABEL_PREFERRED_ANGLE_DEG + step * LABEL_ANGLE_STEP_DEG)
            candidates.append(LABEL_PREFERRED_ANGLE_DEG - step * LABEL_ANGLE_STEP_DEG)

        best_angle     = LABEL_PREFERRED_ANGLE_DEG
        best_box       = None
        best_label_pos = None
        min_overlap    = None

        for angle in candidates:
            angle_mod = angle % 360
            box, label_pos = _label_box_for_angle(lon, lat, angle_mod, leader_km, w_km, h_km)
            overlap_count = sum(
                1 for pb in placed_boxes
                if _boxes_overlap(box, pb, margin_deg_lon, margin_deg_lat)
            )
            if overlap_count == 0:
                best_angle, best_box, best_label_pos = angle_mod, box, label_pos
                break
            if min_overlap is None or overlap_count < min_overlap:
                min_overlap = overlap_count
                best_angle, best_box, best_label_pos = angle_mod, box, label_pos

        placed_boxes.append(best_box)
        results.append((lon, lat, point_id, best_angle, best_label_pos[0], best_label_pos[1], leader_km))

    return results


def build_time_label_layers(label_points, layer_name_prefix, point_type):
    pts_for_algo = [(lon, lat, i) for i, (lon, lat, _) in enumerate(label_points)]
    placed = assign_leader_line_angles(pts_for_algo)

    leader_fields = QgsFields()
    leader_fields.append(QgsField("seq",       QVariant.Int))
    leader_fields.append(QgsField("type",      QVariant.String))
    leader_fields.append(QgsField("time_text", QVariant.String))

    leader_layer = QgsVectorLayer("LineString?crs=EPSG:4326", f"{layer_name_prefix}_Leader", "memory")
    leader_layer.dataProvider().addAttributes(leader_fields)
    leader_layer.updateFields()

    leader_feats = []
    for idx, item in enumerate(placed):
        lon, lat, point_id, angle_deg, label_lon, label_lat, leader_km = item
        time_text = label_points[idx][2]
        if abs(label_lon - lon) < 1e-9 and abs(label_lat - lat) < 1e-9:
            continue
        feat = QgsFeature(leader_fields)
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(lon, lat), QgsPointXY(label_lon, label_lat)]))
        feat.setAttributes([int(point_id), point_type, time_text])
        leader_feats.append(feat)

    leader_layer.dataProvider().addFeatures(leader_feats)
    leader_layer.updateExtents()

    line_style = "solid" if point_type == "Analysis" else "dot"
    leader_layer.renderer().setSymbol(QgsLineSymbol.createSimple({
        "color": "110,110,110,180", "width": "0.25", "line_style": line_style,
    }))

    label_fields = QgsFields()
    label_fields.append(QgsField("seq",       QVariant.Int))
    label_fields.append(QgsField("type",      QVariant.String))
    label_fields.append(QgsField("time_text", QVariant.String))

    label_layer = QgsVectorLayer("Point?crs=EPSG:4326", f"{layer_name_prefix}_Text", "memory")
    label_layer.dataProvider().addAttributes(label_fields)
    label_layer.updateFields()

    label_feats = []
    for idx, item in enumerate(placed):
        lon, lat, point_id, angle_deg, label_lon, label_lat, leader_km = item
        time_text = label_points[idx][2]
        feat = QgsFeature(label_fields)
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(label_lon, label_lat)))
        feat.setAttributes([int(point_id), point_type, time_text])
        label_feats.append(feat)

    label_layer.dataProvider().addFeatures(label_feats)
    label_layer.updateExtents()

    label_layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({
        "name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0",
    }))

    pal = QgsPalLayerSettings()
    pal.fieldName = "time_text"
    pal.enabled   = True
    pal.placement = QgsPalLayerSettings.Free

    text_fmt = QgsTextFormat()
    text_fmt.setSize(7.0)
    text_fmt.setSizeUnit(QgsUnitTypes.RenderPoints)

    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    buf.setColor(QColor(255, 255, 255, 220))
    text_fmt.setBuffer(buf)

    pal.setFormat(text_fmt)
    label_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    label_layer.setLabelsEnabled(True)

    return leader_layer, label_layer


def build_point_fields():
    fields = QgsFields()
    fields.append(QgsField("seq",            QVariant.Int))
    fields.append(QgsField("type",           QVariant.String))
    fields.append(QgsField("datetime",       QVariant.String))
    fields.append(QgsField("forecast_hr",    QVariant.String))
    fields.append(QgsField("lon",            QVariant.Double))
    fields.append(QgsField("lat",            QVariant.Double))
    fields.append(QgsField("max_wind",       QVariant.String))
    fields.append(QgsField("max_gust",       QVariant.String))
    fields.append(QgsField("pressure",       QVariant.String))
    fields.append(QgsField("move_speed",     QVariant.String))
    fields.append(QgsField("move_dir",       QVariant.String))
    fields.append(QgsField("radius_15ms",    QVariant.String))
    fields.append(QgsField("radius_25ms",    QVariant.String))
    fields.append(QgsField("prob_radius",    QVariant.String))
    fields.append(QgsField("move_pred_zh",   QVariant.String))
    fields.append(QgsField("intensity_code", QVariant.String))
    fields.append(QgsField("intensity_zh",   QVariant.String))
    return fields


def make_point_feature(fields, seq, ftype, dt, lon, lat, fix, forecast_hr=""):
    c15 = get_circle(fix, "Circle15ms")
    c25 = get_circle(fix, "Circle25ms")
    intensity_code, intensity_zh, _ = classify_intensity(fix.get("MaxWindSpeed"))
    feat = QgsFeature(fields)
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
    feat.setAttributes([
        seq, ftype, dt, forecast_hr, lon, lat,
        fix.get("MaxWindSpeed", ""),
        fix.get("MaxGustSpeed", ""),
        fix.get("Pressure", ""),
        fix.get("MovingSpeed", ""),
        fix.get("MovingDirection", ""),
        (c15.get("Radius") if c15 else "") or "",
        (c25.get("Radius") if c25 else "") or "",
        fix.get("Radius70PercentProbability", ""),
        get_moving_prediction_zh(fix),
        intensity_code,
        intensity_zh,
    ])
    return feat


def build_radius_fields():
    fields = QgsFields()
    fields.append(QgsField("seq",         QVariant.Int))
    fields.append(QgsField("type",        QVariant.String))
    fields.append(QgsField("datetime",    QVariant.String))
    fields.append(QgsField("forecast_hr", QVariant.String))
    fields.append(QgsField("radius_km",   QVariant.Double))
    fields.append(QgsField("wind_level",  QVariant.String))
    return fields


def make_radius_feature(fields, seq, ftype, dt, forecast_hr, radius_km, wind_level, polygon_pts):
    feat = QgsFeature(fields)
    feat.setGeometry(QgsGeometry.fromPolygonXY([polygon_pts]))
    feat.setAttributes([seq, ftype, dt, forecast_hr, radius_km, wind_level])
    return feat


def create_layers_for_typhoon(typhoon):
    typhoon_name = typhoon.get("CwaTyphoonName") or typhoon.get("TyphoonName", "Typhoon")
    ty_no        = typhoon.get("CwaTyNo") or typhoon.get("CwaTdNo") or "00"
    layer_prefix = f"Typhoon_{ty_no}_{typhoon_name}"

    analysis_fixes = typhoon.get("AnalysisData", {}).get("Fix", [])
    forecast_fixes = typhoon.get("ForecastData", {}).get("Fix", [])
    if not isinstance(analysis_fixes, list):
        analysis_fixes = [analysis_fixes]
    if not isinstance(forecast_fixes, list):
        forecast_fixes = [forecast_fixes]

    point_fields  = build_point_fields()
    radius_fields = build_radius_fields()

    layer_analysis = QgsVectorLayer("Point?crs=EPSG:4326", f"{layer_prefix}_Analysis", "memory")
    layer_analysis.dataProvider().addAttributes(point_fields)
    layer_analysis.updateFields()

    feats_analysis        = []
    analysis_points       = []
    analysis_label_points = []
    radius15_feats        = []
    radius25_feats        = []

    for i, fix in enumerate(analysis_fixes):
        lon = float(fix["CoordinateLongitude"])
        lat = float(fix["CoordinateLatitude"])
        dt  = fix.get("DateTime", "")
        feats_analysis.append(make_point_feature(point_fields, i, "Analysis", dt, lon, lat, fix))
        analysis_points.append((lon, lat))
        analysis_label_points.append((lon, lat, format_time_label(dt)))
        if DRAW_RADIUS_15MS:
            c15 = get_circle(fix, "Circle15ms")
            if c15 and c15.get("Radius"):
                pts = make_geo_circle(lon, lat, float(c15["Radius"]))
                if pts:
                    radius15_feats.append(make_radius_feature(radius_fields, i, "Analysis", dt, "", float(c15["Radius"]), "15ms", pts))
        if DRAW_RADIUS_25MS:
            c25 = get_circle(fix, "Circle25ms")
            if c25 and c25.get("Radius"):
                pts = make_geo_circle(lon, lat, float(c25["Radius"]))
                if pts:
                    radius25_feats.append(make_radius_feature(radius_fields, i, "Analysis", dt, "", float(c25["Radius"]), "25ms", pts))

    layer_analysis.dataProvider().addFeatures(feats_analysis)
    layer_analysis.updateExtents()

    layer_forecast = QgsVectorLayer("Point?crs=EPSG:4326", f"{layer_prefix}_Forecast", "memory")
    layer_forecast.dataProvider().addAttributes(point_fields)
    layer_forecast.updateFields()

    feats_forecast        = []
    forecast_points       = []
    forecast_label_points = []

    for i, fix in enumerate(forecast_fixes):
        lon = float(fix["CoordinateLongitude"])
        lat = float(fix["CoordinateLatitude"])
        dt  = fix.get("InitialTime", "")
        fhr = fix.get("ForecastHour", "")
        feats_forecast.append(make_point_feature(point_fields, i, "Forecast", dt, lon, lat, fix, forecast_hr=fhr))
        forecast_points.append((lon, lat))
        forecast_label_points.append((lon, lat, format_time_label(dt, fhr)))
        if DRAW_RADIUS_15MS:
            c15 = get_circle(fix, "Circle15ms")
            if c15 and c15.get("Radius"):
                pts = make_geo_circle(lon, lat, float(c15["Radius"]))
                if pts:
                    radius15_feats.append(make_radius_feature(radius_fields, i, "Forecast", dt, fhr, float(c15["Radius"]), "15ms", pts))
        if DRAW_RADIUS_25MS:
            c25 = get_circle(fix, "Circle25ms")
            if c25 and c25.get("Radius"):
                pts = make_geo_circle(lon, lat, float(c25["Radius"]))
                if pts:
                    radius25_feats.append(make_radius_feature(radius_fields, i, "Forecast", dt, fhr, float(c25["Radius"]), "25ms", pts))

    layer_forecast.dataProvider().addFeatures(feats_forecast)
    layer_forecast.updateExtents()

    line_fields = QgsFields()
    line_fields.append(QgsField("name",    QVariant.String))
    line_fields.append(QgsField("segment", QVariant.String))

    layer_line = QgsVectorLayer("LineString?crs=EPSG:4326", f"{layer_prefix}_Track", "memory")
    layer_line.dataProvider().addAttributes(line_fields)
    layer_line.updateFields()

    line_feats = []
    if len(analysis_points) >= 2:
        feat = QgsFeature(line_fields)
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in analysis_points]))
        feat.setAttributes([f"{typhoon_name} 過去路徑", "Analysis"])
        line_feats.append(feat)

    connect_points = []
    if analysis_points:
        connect_points.append(analysis_points[-1])
    connect_points.extend(forecast_points)
    if len(connect_points) >= 2:
        feat = QgsFeature(line_fields)
        feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in connect_points]))
        feat.setAttributes([f"{typhoon_name} 預測路徑", "Forecast"])
        line_feats.append(feat)

    layer_line.dataProvider().addFeatures(line_feats)
    layer_line.updateExtents()

    layer_radius15 = None
    layer_radius25 = None

    if DRAW_RADIUS_15MS and radius15_feats:
        layer_radius15 = QgsVectorLayer("Polygon?crs=EPSG:4326", f"{layer_prefix}_Radius15", "memory")
        layer_radius15.dataProvider().addAttributes(radius_fields)
        layer_radius15.updateFields()
        layer_radius15.dataProvider().addFeatures(radius15_feats)
        layer_radius15.updateExtents()

    if DRAW_RADIUS_25MS and radius25_feats:
        layer_radius25 = QgsVectorLayer("Polygon?crs=EPSG:4326", f"{layer_prefix}_Radius25", "memory")
        layer_radius25.dataProvider().addAttributes(radius_fields)
        layer_radius25.updateFields()
        layer_radius25.dataProvider().addFeatures(radius25_feats)
        layer_radius25.updateExtents()

    layer_current = None
    if analysis_fixes:
        current_fields = QgsFields()
        current_fields.append(QgsField("name",         QVariant.String))
        current_fields.append(QgsField("datetime",     QVariant.String))
        current_fields.append(QgsField("max_wind",     QVariant.String))
        current_fields.append(QgsField("pressure",     QVariant.String))
        current_fields.append(QgsField("intensity_zh", QVariant.String))
        current_fields.append(QgsField("info_text",    QVariant.String))

        last_fix = analysis_fixes[-1]
        lon = float(last_fix["CoordinateLongitude"])
        lat = float(last_fix["CoordinateLatitude"])
        _, intensity_zh, _ = classify_intensity(last_fix.get("MaxWindSpeed"))
        info_text = (
            f"{typhoon_name} / {intensity_zh} / "
            f"{last_fix.get('MaxWindSpeed','?')} m/s / "
            f"{last_fix.get('Pressure','?')} hPa"
        )

        layer_current = QgsVectorLayer("Point?crs=EPSG:4326", f"{layer_prefix}_CurrentPosition", "memory")
        layer_current.dataProvider().addAttributes(current_fields)
        layer_current.updateFields()

        feat = QgsFeature(current_fields)
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttributes([
            typhoon_name, last_fix.get("DateTime", ""),
            last_fix.get("MaxWindSpeed", ""), last_fix.get("Pressure", ""),
            intensity_zh, info_text,
        ])
        layer_current.dataProvider().addFeatures([feat])
        layer_current.updateExtents()

    layer_time_leader_analysis, layer_time_label_analysis = build_time_label_layers(
        analysis_label_points, f"{layer_prefix}_TimeLabel_Analysis", "Analysis"
    )
    layer_time_leader_forecast, layer_time_label_forecast = build_time_label_layers(
        forecast_label_points, f"{layer_prefix}_TimeLabel_Forecast", "Forecast"
    )

    return {
        "name": typhoon_name, "ty_no": ty_no,
        "analysis": layer_analysis,
        "forecast": layer_forecast,
        "line":     layer_line,
        "radius15": layer_radius15,
        "radius25": layer_radius25,
        "current":  layer_current,
        "time_leader_analysis": layer_time_leader_analysis,
        "time_label_analysis":  layer_time_label_analysis,
        "time_leader_forecast": layer_time_leader_forecast,
        "time_label_forecast":  layer_time_label_forecast,
    }


def build_intensity_categorized_renderer(point_shape, outline_only=False):
    categories = []
    for lo, hi, code, label, color in INTENSITY_CATEGORIES:
        if outline_only:
            props = {
                "name": point_shape, "color": "255,255,255,200",
                "outline_color": color, "outline_width": "0.8", "size": "3.6",
            }
        else:
            props = {
                "name": point_shape, "color": color,
                "outline_color": "0,0,0,255", "outline_width": "0.3", "size": "3.2",
            }
        categories.append(QgsRendererCategory(code, QgsMarkerSymbol.createSimple(props), label))
    fallback = QgsMarkerSymbol.createSimple({
        "name": point_shape, "color": "180,180,180,255",
        "outline_color": "0,0,0,255", "outline_width": "0.3", "size": "3.0",
    })
    categories.append(QgsRendererCategory("UNKNOWN", fallback, "未知"))
    return QgsCategorizedSymbolRenderer("intensity_code", categories)


def style_analysis_layer(layer):
    layer.setRenderer(build_intensity_categorized_renderer("circle", outline_only=False))
    layer.triggerRepaint()


def style_forecast_layer(layer):
    layer.setRenderer(build_intensity_categorized_renderer("circle", outline_only=True))
    layer.triggerRepaint()


def style_line_layer(layer):
    categories = [
        QgsRendererCategory("Analysis", QgsLineSymbol.createSimple({"color": "70,82,94,255", "width": "0.7", "line_style": "solid"}), "過去路徑"),
        QgsRendererCategory("Forecast",  QgsLineSymbol.createSimple({"color": "70,82,94,200", "width": "0.6", "line_style": "dash"}),  "預測路徑"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("segment", categories))
    layer.triggerRepaint()


def style_radius_layer(layer, color_rgba, label):
    base_rgb = color_rgba.rsplit(",", 1)[0]
    categories = [
        QgsRendererCategory("Analysis", QgsFillSymbol.createSimple({
            "color": color_rgba,
            "outline_color": base_rgb + ",180", "outline_width": "0.4",
        }), f"{label}(現在)"),
        QgsRendererCategory("Forecast", QgsFillSymbol.createSimple({
            "color": base_rgb + ",35",
            "outline_color": base_rgb + ",150", "outline_width": "0.4", "outline_style": "dash",
        }), f"{label}(預測)"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("type", categories))
    layer.triggerRepaint()


def style_current_position_layer(layer):
    symbol = QgsMarkerSymbol()
    symbol.deleteSymbolLayer(0)

    outer_ring = QgsSimpleMarkerSymbolLayer()
    outer_ring.setShape(QgsSimpleMarkerSymbolLayer.Circle)
    outer_ring.setSize(8)
    outer_ring.setColor(QColor(255, 255, 255, 0))
    outer_ring.setStrokeColor(QColor(211, 47, 47, 255))
    outer_ring.setStrokeWidth(0.9)

    inner_dot = QgsSimpleMarkerSymbolLayer()
    inner_dot.setShape(QgsSimpleMarkerSymbolLayer.Circle)
    inner_dot.setSize(3.2)
    inner_dot.setColor(QColor(211, 47, 47, 255))
    inner_dot.setStrokeColor(QColor(211, 47, 47, 255))
    inner_dot.setStrokeWidth(0)

    symbol.appendSymbolLayer(outer_ring)
    symbol.appendSymbolLayer(inner_dot)
    layer.renderer().setSymbol(symbol)
    layer.setLabelsEnabled(False)
    layer.triggerRepaint()


def main():
    print("正在抓取颱風資料...")
    data = fetch_typhoon_json()

    if data.get("success") not in ("true", True):
        raise RuntimeError("API 回傳失敗，請檢查 API_KEY 是否正確。")

    typhoons = pick_typhoons(data)
    if not typhoons:
        print("目前沒有符合條件的活動颱風資料。")
        return []

    print(f"共取得 {len(typhoons)} 個颱風資料，開始繪製...")

    project     = QgsProject.instance()
    all_extents = []
    results     = []

    for typhoon in typhoons:
        info = create_layers_for_typhoon(typhoon)
        print(f"  -> {info['name']} (編號 {info['ty_no']})")

        style_analysis_layer(info["analysis"])
        style_forecast_layer(info["forecast"])
        style_line_layer(info["line"])
        if info["radius15"] is not None:
            style_radius_layer(info["radius15"], "224,135,62,65", "七級風暴風圈")
        if info["radius25"] is not None:
            style_radius_layer(info["radius25"], "178,58,52,75", "十級風暴風圈")
        if info["current"] is not None:
            style_current_position_layer(info["current"])

        if info["radius15"] is not None:
            project.addMapLayer(info["radius15"])
            all_extents.append(info["radius15"].extent())
        if info["radius25"] is not None:
            project.addMapLayer(info["radius25"])
            all_extents.append(info["radius25"].extent())

        project.addMapLayer(info["line"])
        project.addMapLayer(info["analysis"])
        project.addMapLayer(info["forecast"])

        if info["current"] is not None:
            project.addMapLayer(info["current"])
            all_extents.append(info["current"].extent())

        project.addMapLayer(info["time_leader_analysis"])
        project.addMapLayer(info["time_label_analysis"])
        project.addMapLayer(info["time_leader_forecast"])
        project.addMapLayer(info["time_label_forecast"])

        all_extents.append(info["line"].extent())
        all_extents.append(info["analysis"].extent())
        all_extents.append(info["forecast"].extent())

        results.append(info)

    from qgis.utils import iface
    if iface is not None and all_extents:
        canvas = iface.mapCanvas()
        combined_extent = all_extents[0]
        for ext in all_extents[1:]:
            combined_extent.combineExtentWith(ext)
        combined_extent.scale(1.3)
        canvas.setExtent(combined_extent)
        canvas.refresh()

    print(f"完成！已建立 {len(results)} 個颱風的路徑、暴風圈、時間標籤圖層。")
    return results


if __name__ == "__console__" or __name__ == "__main__":
    main()
