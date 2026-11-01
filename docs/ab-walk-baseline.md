# A／B Walk 原型基線

2026-11-01，Windows、專案 `.venv` Python 3.12；使用解壓在 `build/handoff-review-20261101` 的副本，未重建或修改原始附件樣本。

- 原始測試：25 項中 23 通過、1 失敗、1 跳過。失敗測試把 `/tmp/absolute_body.png` 當作 Windows 上的絕對路徑；此字串在 Windows 並非完整的跨磁碟絕對路徑。
- 在解壓副本的測試中將此測試資料改為 `os.path.abspath(...)`，並與生成的來源值比較後，重跑結果為 24 通過、1 跳過。跳過的是此環境不支援的符號連結測試；這只修正測試資料，並不證明任意外部路徑是安全的。
- Schematic 與 Arcane 原型 CLI 在新輸出資料夾各成功生成 8 幀 PNG、sheet、GIF、guide、metadata。原型 GUI 未實際操作。
- 交接原型尚未接入 Sprite Studio，原型接受的外部路徑需要在整合時增加專案內路徑限制。單張合併圖片的隱藏部位仍需補畫。
