# 🌀 QGIS 颱風路徑自動繪製

在 QGIS 中，一鍵從中央氣象署開放資料 API 抓取颱風資料並自動繪製完整路徑圖層。

---

## 功能特色

- **即時資料**：直接呼叫中央氣象署（CWA）開放資料 API，取得所有活動中颱風的過去定位與未來預測路徑
- **多颱風支援**：可同時繪製多個颱風，或指定單一颱風編號 / 名稱
- **強度分級配色**：依近中心最大風速（m/s）自動套用漸層色階
  - 🟢 熱帶性低氣壓（< 17.2 m/s）
  - 🟡 輕度颱風（17.2–32.6 m/s）
  - 🟠 中度颱風（32.7–50.9 m/s）
  - 🔴 強烈颱風（≥ 51.0 m/s）
- **暴風圈**：自動繪製七級風（15 m/s）與十級風（25 m/s）暴風圈，並依緯度做 cos 修正避免橢圓變形
- **目前位置標示**：紅色雙層同心圓符號，標示最新定位點
- **時間標籤 + 自動避碰引線**：每個路徑點旁附上時間標籤，以避碰演算法自動調整引線角度，防止文字重疊
  - 過去路徑標籤顯示實際定位時間
  - 預測路徑標籤顯示預報有效時間（發報時間 + 預報時數）
- **自動縮放**：圖層建立後自動縮放至所有颱風的合併範圍

---

## 建立的圖層

每個颱風會產生以下圖層：

| 圖層名稱 | 說明 |
|---|---|
| `Typhoon_<編號>_<名稱>_Analysis` | 過去定位路徑點（實心，依強度配色） |
| `Typhoon_<編號>_<名稱>_Forecast` | 預測路徑點（空心，依強度配色） |
| `Typhoon_<編號>_<名稱>_Track` | 路徑連線（過去=實線，預測=虛線） |
| `Typhoon_<編號>_<名稱>_Radius15` | 七級風暴風圈（半透明橘色多邊形） |
| `Typhoon_<編號>_<名稱>_Radius25` | 十級風暴風圈（半透明深紅色多邊形） |
| `Typhoon_<編號>_<名稱>_CurrentPosition` | 最新定位點（紅色雙層圓環） |
| `Typhoon_<編號>_<名稱>_TimeLabel_Analysis_Leader` | 過去路徑時間引線 |
| `Typhoon_<編號>_<名稱>_TimeLabel_Analysis_Text` | 過去路徑時間標籤文字 |
| `Typhoon_<編號>_<名稱>_TimeLabel_Forecast_Leader` | 預測路徑時間引線 |
| `Typhoon_<編號>_<名稱>_TimeLabel_Forecast_Text` | 預測路徑時間標籤文字 |

---

## 環境需求

- **QGIS** 3.x（開發與測試版本：3.44.4）
- Python 3.x（QGIS 內建）
- 網路連線（使用 API 模式時）
- 中央氣象署開放資料平台帳號與 API 金鑰

---

## 取得 API 金鑰

1. 前往 [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)
2. 註冊帳號並登入
3. 至「會員中心」取得您的 **Authorization Key**
4. 使用的資料集：`W-C0034-005`（颱風路徑）

---

## 使用方式

1. 開啟 QGIS
2. 點選選單 **外掛 (Plugins) → Python 主控台 (Python Console)**
3. 點選「**顯示編輯器**」開啟程式碼編輯區
4. 貼上 `main.py` 的完整內容
5. 修改位於第31行的 `API_KEY` 值：

```python
API_KEY = "你的-API-KEY-貼在這裡"
```

6. 按 **Ctrl+Enter** 或點選「執行」按鈕

---

## 主要設定參數

腳本頂端可調整以下參數：

```python
ALL_TYPHOONS = True           # True = 繪製所有活動颱風；False = 指定單一颱風
TARGET_TYPHOON_NO = None      # 例如 "07"，ALL_TYPHOONS=False 時才生效
TARGET_TYPHOON_NAME = None    # 例如 "MEKKHALA"，ALL_TYPHOONS=False 時才生效

DRAW_RADIUS_15MS = True       # 是否繪製七級風暴風圈
DRAW_RADIUS_25MS = True       # 是否繪製十級風暴風圈
RADIUS_CIRCLE_SEGMENTS = 64   # 暴風圈多邊形邊數（越多越圓滑）
```

若要使用本機 JSON 檔（例如已用 curl 下載好的資料）：

```python
USE_LOCAL_FILE = True
LOCAL_JSON_PATH = "/path/to/your/typhoon.json"
```

---

## 檔案說明

```
main.py         主程式，請貼入 QGIS Python 主控台執行
README.md       本說明文件
LICENSE         授權文件  
```

---

## 授權

本專案以 [GPL License](LICENSE) 釋出。

---

## 致謝

- 資料來源：[中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)
- 開發環境：[Python](https://www.python.org/downloads/)&[QGIS](https://qgis.org/)
