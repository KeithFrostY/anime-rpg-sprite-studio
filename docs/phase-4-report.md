# Phase 4 completion report — 2026-10-29

## 已完成功能

- 目前角色完整 Walk 匯出：16 張 256×256 RGBA PNG、1024×1024 RGBA
  Sprite Sheet、動畫 JSON，共 18 個檔案。
- 固定方向列序 Front、Left、Right、Back；每列幀 0–3，不縮放、裁邊或去背。
- JSON 格式版本 1：角色、FPS、循環、有理數幀時長、幀路徑、矩形、腳底 Pivot、
  明確座標原點。格式與專案 schema 2 分離。
- 背景驗證全部素材後才允許匯出；背景寫入、合成、驗證及進度回報。
- 匯出內容採不可變快照，保留半透明像素，不修改或強制儲存來源專案。
- 暫存目錄寫入後驗證像素／JSON，最後一次發布新 UUID 子資料夾。
  不覆蓋既有匯出，取消或錯誤清理暫存；關閉時等待工作完成。
- 完成後由使用者點選開啟資料夾。晚於發布的取消正確回報完成。
- 依使用者修訂，不建立任何 Unity 匯出、匯入工具或引擎專用資產。

## 修改的檔案

- AGENTS.md：記錄取消 Unity 匯出要求。
- export/__init__.py；新增 export/service.py。
- ui/main_window.py；新增 ui/export_worker.py、ui/export_dialog.py。
- 新增 tests/test_phase4.py、tests/test_phase4_ui.py、tests/smoke_phase4.py。
- README.md、docs/architecture.md。
- 新增 docs/phase-4-plan.md、export-format.md、本報告、phase-4-preview.png、
  phase-4-sheet.png。
- 新增 examples/export-demo/README.md 與 walk-0eb603907ded4c9a8ae4dc919bc99ef7/
  下的 18 個實際匯出檔案。

## 測試方式與結果

- 環境：Windows、Python 3.12.14、PySide6 6.12.0、Pillow 13.0.0。
- 核心實作前 11 項測試因缺少功能失敗；GUI 實作前 4 項測試失敗。
- 最終 `.venv/Scripts/python.exe -m pytest -q --tb=short`：63 passed in 23.84s。
- 新增 16 項測試，涵蓋：Sheet 每格像素與半透明 alpha、不重複套用透明度、
  JSON FPS／循環／時長／Pivot／矩形、不可變快照、缺失／損毀／錯誤尺寸／
  越界素材、取消、寫入／發布失敗清理、不覆蓋既有目的地、發布後取消仍成功、
  視窗驗證狀態、關閉等候取消、完成後明確點選開啟資料夾。
- `.venv/Scripts/python.exe tests/smoke_phase4.py --keep-example`：PASS。
  實際 Qt 視窗完成全部驗證、背景匯出與進度顯示，產生可查看的 18 檔範例。
  匯出視窗與 Sheet 快照已目視檢查。
- compileall 通過；pip check：No broken requirements found。
- 獨立審查未發現重要問題，另實測原生視窗關閉會等待背景取消完成。
- 開啟資料夾按鈕以 Qt 呼叫測試驗證；本次未實際啟動檔案總管。
- 未新增依賴、付費服務、真實 API 請求、Key、GPU 或本機 AI 模型。

## 尚未完成事項

- Phase 5–6：真實 fal.ai、Windows 憑證後端、持久化 BudgetManager、
  一致性優化、打包均未實作。Unity 匯出已移除範圍。
- 不提供匯出格式勾選、覆蓋舊版本、匯出後重新匯入 JSON 或批次多角色匯出。
- 未全面手動測試高 DPI、多螢幕、網路磁碟與突發斷電。

## 技術風險與決定

- 目標為 Windows；發布依賴 Windows 的同目錄、拒絕覆蓋 rename 行為，
  不宣稱其他作業系統／網路磁碟有同樣原子性或耐久性。
- 正常取消／失敗會清理暫存，但強制終止／斷電可能留下暫存資料夾；
  若磁碟損壞或權限改變，清理本身亦可能失敗並回報錯誤。
- 每次建立新的 UUID 目錄，不取代舊匯出，磁碟版本需人工整理。
- 匯出固定使用驗證後快照，外部修改圖片需重新驗證，不會在寫檔途中重讀。
- 保留原始像素與固定 Pivot，不修補 Phase 3 的接縫、腳滑或已裁切內容。
- 使用者工作區沒有 Git 儲存庫，未建立提交。

## 下一步建議

先檢查匯出 PNG／Sheet／JSON 是否適合工作流程，再另行規劃 Phase 5 的
fal.ai、CredentialManager 與 BudgetManager。價格須於整合時查證官方資訊，
每筆付費請求仍需使用者明確確認；不得自動進入下一階段或提交付費工作。
