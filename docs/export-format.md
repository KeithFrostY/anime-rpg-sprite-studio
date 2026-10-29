# PNG／Sprite Sheet／動畫 JSON 匯出

先選擇已有四方向完整 Walk 的角色，按主視窗「匯出…」，或檔案選單的匯出。
匯出視窗會驗證全部 16 張素材；任一張缺失、損毀、尺寸錯誤或路徑越界，
均不可匯出。圖片使用 CPU 解碼與合成，不呼叫 AI，不需 Key。

## 操作

1. 確認角色、FPS 與循環設定。匯出取目前記憶體中的角色資料快照，
   包括尚未儲存的名稱與 FPS，但必須先有已儲存專案位置供素材定位。
2. 等待 16 幀驗證完成，選擇現有輸出資料夾。
3. 按「匯出全部檔案」；每次建立新的 `walk-<隨機識別碼>` 子資料夾。
4. 完成後可按「開啟輸出資料夾」；不會自動啟動檔案總管。

匯出不會儲存或修改原專案。若外部程式改動素材，可按「重新驗證」更新
已捕捉的圖片內容；視窗內角色名稱、FPS 等仍是開啟視窗時的快照。
一次匯出三種格式，沒有 Unity 工具、引擎專用資產或 `.meta`。

## 檔案結構

```text
walk-<id>/
├─ animation.json
├─ walk_sheet.png
└─ frames/
   ├─ walk_front_0.png ... walk_front_3.png
   ├─ walk_left_0.png  ... walk_left_3.png
   ├─ walk_right_0.png ... walk_right_3.png
   └─ walk_back_0.png  ... walk_back_3.png
```

總共 18 個檔案。獨立 PNG 固定 256×256 RGBA；Sheet 固定 1024×1024 RGBA。
Sheet 由上至下是 Front、Left、Right、Back，每列由左至右為幀 0–3。
不縮放、裁邊、加邊或自動去背，保留原素材的透明度。檔名不使用角色名稱，
避免中文、斜線及 Windows 保留名稱造成檔案問題；名稱保存在 JSON 中。

## JSON 版本 1

- `format`：`anime-rpg-sprite-studio-walk`。
- `format_version`：`1`；這是匯出格式版本，與專案 schema 2 分開。
- `character`：角色 id、name；不包含原始素材路徑、專案絕對路徑或憑證。
- `animation`：name=`Walk`、fps、loop、frames_per_direction=`4`，以及
  `frame_duration_seconds={numerator:1,denominator:fps}`，以有理數表達幀時長。
- `frame_size`：width、height 均為 256。
- `sheet`：圖片檔名、寬高、4 欄 4 列、`coordinate_origin="top_left"`、row_order。
- `pivot`：`x=0.5`、`y=0.0`、`normalized=true`、`coordinate_origin="bottom_left"`。
- `directions`：有順序的四個方向物件；各含 name 與有順序的四個 frames。

每幀範例：

```json
{
  "index": 2,
  "file": "frames/walk_left_2.png",
  "rect": {"x": 512, "y": 256, "width": 256, "height": 256}
}
```

`file` 相對於匯出資料夾；`rect` 是 Sheet 左上原點像素矩形，範圍為
`[x,x+width)`、`[y,y+height)`。Pivot 是每幀左下原點的標準化位置，
不可將其直接當成 Sheet 左上原點像素座標。Pivot 在下邊界中心，
不代表檢測或修正了角色實際腳底位置。

## 取消與錯誤

所有輸出先寫入所選目錄下私有的 `.sprite-export-…` 暫存資料夾，
重新讀取並比對 JSON、PNG 規格及 Sheet 每格像素後，才在 Windows 上
以資料夾重新命名一次發布成完整匯出。既有目的地一律拒絕覆蓋。

驗證、寫入或發布失敗，以及發布前的取消，會清理暫存目錄並保留既有匯出。
關閉忙碌中的視窗會要求取消並等候工作結束。若取消到達時已完成發布，
結果回報為完成，保留成功輸出的資料夾；不會刪除已發布檔案。
程式被強制終止或突然斷電可能留下暫存目錄；不會自動掃描或刪除其他目錄。
磁碟故障或權限改變也可能讓清理失敗，介面將回報錯誤。

目前只保證目標 Windows 的發布行為，未驗證其他作業系統或網路磁碟的
原子性／耐久性。新資料夾不會取代舊匯出，請自行整理不再需要的版本。
