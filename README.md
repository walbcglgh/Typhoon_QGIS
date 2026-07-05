# 🌀 Typhoon_QGIS

在 QGIS 中一鍵繪製颱風路徑的工具集，包含兩支獨立的腳本：

| 腳本 | 資料來源 | 呈現內容 |
|---|---|---|
| [`main.py`](#1-mainpy--官方路徑與暴風圈) | 中央氣象署（CWA）開放資料 | 官方「過去路徑 + 預測路徑」單一路徑，含暴風圈、標籤 |
| [`fnv3.py`](#2-fnv3py---fnv3-系集預報路徑) | Google Weather Lab（FNV3 模式） | AI 系集預報，50 個成員的路徑分布（機率/不確定性範圍） |

兩支腳本互相獨立，可以只用其中一支，也可以同時載入同一個 QGIS 專案疊圖比較「官方預測」與「AI 系集預報」的差異。

---

## 環境需求

- **QGIS** 3.x
- **Python** 3.x（QGIS 內建，不需另外安裝）
- 兩支腳本都是在 QGIS 的 **Plugins → Python Console** 貼上執行，不能用一般的 Python 直譯器單獨執行

---

## 1. `main.py` — 官方路徑與暴風圈

在 QGIS 中，一鍵從中央氣象署開放資料 API 抓取颱風資料並自動繪製完整路徑圖層。

### 詳細功能

- **即時資料同步**：直接呼叫中央氣象署（CWA）開放資料 API，取得所有活動中颱風的定位與預測路徑。
- **強度分級視覺化**：依近中心最大風速（m/s）自動套用標準色階：
  - 🟢 熱帶性低氣壓（< 17.2 m/s）
  - 🟡 輕度颱風（17.2–32.6 m/s）
  - 🟠 中度颱風（32.7–50.9 m/s）
  - 🔴 強烈颱風（≥ 51.0 m/s）
- **路徑顯示優化**：
  - **過去路徑**：僅保留路徑連線與定位點，保持畫面簡潔。
  - **預測路徑**：自動繪製預測的七級風（15 m/s）與十級風（25 m/s）暴風圈。
- **進階標籤系統**：
  - **豐富內容**：標籤同時顯示「中文名稱」、「編號」、「國際命名」及「時間」。
  - **優質字型**：預設支援「jf open 粉圓」字型，字體更大、更清晰。
  - **自動避碰引線**：內建演算法自動計算引線角度，防止多個路徑點標籤互相重疊。
- **自動縮放**：圖層建立後自動縮放至所有颱風的合併影響範圍。

### 建立的圖層結構

| 圖層名稱 | 說明 |
|---|---|
| `Typhoon_<編號>_<名稱>_Analysis` | 過去定位點（實心，依強度配色） |
| `Typhoon_<編號>_<名稱>_Forecast` | 預測路徑點（空心，依強度配色） |
| `Typhoon_<編號>_<名稱>_Track` | 路徑連線（過去=實線，預測=虛線） |
| `Typhoon_<編號>_<名稱>_Radius15` | **預測**七級風暴風圈（半透明橘色多邊形） |
| `Typhoon_<編號>_<名稱>_Radius25` | **預測**十級風暴風圈（半透明深紅色多邊形） |
| `Typhoon_<編號>_<名稱>_CurrentPosition` | 最新定位點（紅色雙層同心圓） |
| `Typhoon_<編號>_<名稱>_TimeLabel_...` | 包含自動引線（Leader）與標籤文字（Text）的圖層組 |

### 額外需求

- **API 金鑰**：需具備中央氣象署開放資料平台帳號。
- **字型檔**：建議準備 `jf-openhuninn-1.1.ttf` 以獲得最佳視覺效果。

### 使用方式

1. **取得 API 金鑰**：至 [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/) 取得您的 Authorization Key。
2. **開啟 QGIS 控制台**：點選 **外掛 (Plugins) → Python 主控台 (Python Console)**。
3. **配置參數**：
   - 在腳本頂端修改 `API_KEY`。
   - 設定 `FONT_PATH` 為您的字型檔案路徑（預設支援 `jf open 粉圓`）。
4. **執行腳本**：將 `main.py` 內容貼入編輯器並按下執行（Ctrl+Enter）。

### 主要設定變數

```python
API_KEY = "你的-API-KEY"
FONT_PATH = "字型檔案路徑"  # 例如 "/path/to/jf-openhuninn-1.1.ttf"

ALL_TYPHOONS = True        # 是否繪製所有活動颱風
DRAW_RADIUS_15MS = True    # 是否繪製七級風暴風圈（僅限預測段）
DRAW_RADIUS_25MS = True    # 是否繪製十級風暴風圈（僅限預測段）
```

---

## 2. `fnv3.py` — FNV3 系集預報路徑

讀取從 [Google Weather Lab](https://deepmind.google.com/science/weatherlab) 下載的 FNV3 颱風系集預報 CSV 檔案，在 QGIS 裡自動畫出每個系集成員（ensemble member）的預報路徑，並依風速等級上色，效果類似 Weather Lab 網站上的路徑圖。

跟 `main.py` 呈現「一條官方預測路徑」不同，這支腳本呈現的是 **50 個系集成員** 的路徑分布，可以看出 AI 模式對未來路徑的不確定性範圍（越發散代表越不確定）。

### 資料來源

1. 到 [Weather Lab](https://deepmind.google.com/science/weatherlab) 
2. 選擇 FNV3 模式、想看的颱風
3. 複製該次預報的 CSV 下載連結（類似 `https://deepmind.google.com/science/weatherlab/download/cyclones/FNV3/ensemble/paired/csv/FNV3_2026_07_04T06_00_paired.csv`），或直接下載存檔

CSV 內容包含以下欄位（節錄）：

| 欄位 | 說明 |
|---|---|
| `track_id` | 颱風編號，例如 `WP092026` |
| `sample` | 系集成員編號 (0~49，共 50 個成員) |
| `lead_time_hours` | 預報時效（第幾小時） |
| `lat` / `lon` | 該時刻的中心緯度／經度 |
| `minimum_sea_level_pressure_hpa` | 中心最低海平面氣壓 |
| `maximum_sustained_wind_speed_knots` | 最大持續風速（節） |

### 使用方式

1. 打開 QGIS
2. 上方選單 `Plugins` → `Python Console`
3. 打開 `fnv3`，把最上面的 `CSV_SOURCE` 改成想讀取的資料來源，支援兩種寫法：

   - **直接填下載連結**（最方便，不用手動下載檔案）：

     ```python
     CSV_SOURCE = "https://deepmind.google.com/science/weatherlab/download/cyclones/FNV3/ensemble/paired/csv/FNV3_2026_07_04T06_00_paired.csv"
     ```

   - **填本機檔案路徑**（如果已經下載存在電腦上）：

     ```python
     CSV_SOURCE = "C:/Users/xxx/Downloads/FNV3_2026_07_04T06_00_paired.csv"
     ```

4. 把整份程式碼貼進 Python Console，按 Enter 執行
5. 圖層面板會出現一個新圖層（預設名稱 `FNV3_Ensemble_Tracks`），裡面就是所有系集成員的路徑

### 參數說明

| 參數 | 說明 | 預設值 |
|---|---|---|
| `CSV_SOURCE` | CSV 資料來源，可填 Weather Lab 的下載連結(URL)，或本機檔案路徑 | (需自行填入) |
| `TRACK_ID_FILTER` | 只畫特定颱風，例如 `"WP092026"`；設 `None` 表示全部颱風都畫 | `None` |
| `LAYER_NAME` | 圖層名稱 | `"FNV3_Ensemble_Tracks"` |
| `COLOR_MODE` | 上色模式，`"wind_category"`（依風速等級上色）或 `"track"`（依颱風編號隨機上色） | `"wind_category"` |
| `LINE_WIDTH` | 路徑線寬 (mm) | `0.35` |
| `LINE_ALPHA` | 線的透明度 (0~255，數字越小越透明) | `160` |
| `SHOW_POINTS` | `1` = 額外畫出每個時間點的點圖層；`0` = 只畫線 | `0` |
| `POINT_SIZE` | 點的大小 (mm)，`SHOW_POINTS=1` 時才有作用 | `1.2` |

### 風速等級配色

`COLOR_MODE = "wind_category"` 時，路徑會依當時風速落在哪個等級上色，對應 Weather Lab 網站的 Wind Speed Legend：

| 等級 | 風速 (節) | 顏色 |
|---|---|---|
| Tropical Depression | < 34 | 🔵 藍 |
| Tropical Storm | 34~63 | 🟢 綠 |
| Category 1 | 64~82 | 🟡 黃 |
| Category 2 | 83~95 | 🟠 橙 |
| Category 3 | 96~112 | 🔴 紅橙 |
| Category 4 | 113~136 | 🟣 洋紅 |
| Category 5 | ≥ 137 | 🟣 紫 |

原始資料是逐點（逐個時間點）的中心位置與風速，腳本會把相鄰兩點連成一小段線，每段依兩端點風速的平均值決定顏色，多段線接起來就會呈現風速隨路徑變化的效果。

### 常見問題

**Q: 執行後說找不到欄位標題列 (init_time,...) ？**
A: 請確認 CSV 檔案是直接從 Weather Lab 下載、未經修改的原始檔案（檔案開頭會有幾行版權聲明的註解）。

**Q: 想同時比較不同時間發布的預報（例如今天早上 vs 昨天晚上）？**
A: 目前腳本一次只讀一個 CSV。若要疊圖比較，可以把腳本執行兩次（改變 `CSV_SOURCE` 和 `LAYER_NAME` 後各執行一次），兩個圖層就會同時顯示在地圖上。

**Q: 想看單一颱風、單一系集成員的路徑就好？**
A: 把 `TRACK_ID_FILTER` 設成該颱風的 `track_id`，並在 QGIS 圖層屬性表用篩選器（Filter）依 `sample` 欄位篩出特定成員。

---

## 授權與致謝

- **授權**：本專案採用 [GPL-3.0 License](./LICENSE)。
- **資料來源**：
  - [中央氣象署開放資料平台](https://opendata.cwa.gov.tw/)（`main.py`）
  - [Google Weather Lab](https://deepmind.google.com/science/weatherlab)（`fnv3.py`，使用需遵守其 [Terms of Use](https://storage.googleapis.com/weathernext-public/terms-of-use.pdf)）
- **推薦字型**：[jf open 粉圓](https://github.com/justfont/open-huninn-font)（`main.py` 標籤字型）
