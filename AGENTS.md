# Anime RPG Sprite Studio

- 僅執行使用者核准階段；先計劃、確認，再實作。
- Python 3.12、PySide6、Pillow、pytest；CPU only。
- 禁止本機 AI 模型、CUDA、GPU 訓練及推理。
- core 不依賴 Qt、HTTP、keyring；AI 與動畫引擎分離。
- 固定 Front/Left/Right/Back，各 4 幀，256×256 RGBA，4×4 Sheet，腳底中心 Pivot；FPS 預設 8。
- Phase 4 只匯出獨立 PNG、Sprite Sheet、動畫 JSON；使用者已取消 Unity 匯出，不建立 Unity 工具或整合。
- 預設離線 Mock；測試禁止真實 Key、網路與付費請求。
- 每次付費請求都需使用者明確確認；禁止自動重試、升級模型、新增付費服務。
- 金額 Decimal；UTC 月份；US$5 月預算、US$4.50 安全停止；未知費用保留，官方有效報價是前提。
- 預算管理無法保證供應商帳單硬上限。
- Key 僅由 keyring 的 Windows 安全後端保存；不可放原始碼、JSON、日誌、測試或 Git。
- Key 僅傳送指定 Provider HTTPS 主機，不允許跨主機帶憑證重新導向。
- 每階段回報：功能、修改檔案、測試方式與結果、未完成事項、風險、下一步。
- 未跑測試不得宣稱通過；未啟動不得宣稱可執行。
