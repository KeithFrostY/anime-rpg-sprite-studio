# Phase 5 completion report — 2026-10-29

## 已完成功能

- 一個真實 fal.ai adapter：FLUX.1 Schnell，256×256、每次一張 PNG、四步、
  安全檢查開啟。保留並預設離線 Mock；沒有其他付費 Provider 或模型。
- 即時官方價格讀取、USD／已知計費單位檢查、兩分鐘報價、請求與 Key 指紋
  綁定；無永久硬編碼的正式費率，無有效報價即禁止付費。
- WindowsCredentialManager 明確選取 keyring WinVaultKeyring，遮罩新增／更換、
  刪除、本機不顯示既有 Key、只讀價格測試 Key；不回退明文或環境變數。
- SQLiteBudgetManager：Decimal 字串、UTC 月分、報價、雜湊單次確認 token、
  請求、實際費用與稽核事件；US$5 預算、US$4.50 安全停止門檻。
- BEGIN IMMEDIATE 跨程序序列化保留與提交；同時只允許一筆執行中／未決請求。
  提交前持久化 SUBMITTING，逾時／取消／不明結果保留費用，禁止自動重送。
- 明確 Yes 後提交一次、原請求狀態／結果查詢、供應商取消、逐筆帳單核對。
  查不到費用絕不當作零；零費用需匹配官方事件。
- 費用待重核與工作狀態獨立；跨月調整保留既有證據、攔截新保留及已保留提交。
- stdlib HTTPS client：TLS 驗證、無重新導向／重試／環境代理、主機允許清單、
  逾時與回應大小限制；CDN 圖片下載不附 Key；GUI 不顯示原始錯誤內容。
- AI 候選、憑證設定、預算摘要、請求紀錄與恢復介面；背景執行網路工作。
  候選獨立另存，不自動覆蓋動畫。主程式啟動不讀 Key 或連網。

## 修改的檔案

- ai/contracts.py、新增 ai/http.py、fal_provider.py、session.py。
- 新增 billing/manager.py；更新 billing/contracts.py。
- 新增 security/credentials.py。
- 新增 ui/ai_worker.py、credentials_dialog.py、ai_dialog.py；更新 ui/main_window.py。
- 新增 tests/conftest.py（封鎖網路／真實 WinVault）、test_phase5_billing.py、
  test_phase5_security.py、test_phase5_provider.py、test_phase5_ui.py、smoke_phase5.py。
- README.md、.gitignore、docs/architecture.md。
- 新增 docs/phase-5-plan.md、ai-usage.md、phase-5-preview.png、本報告。

## 測試方式與結果

- Windows、Python 3.12.14、PySide6 6.12.0；沒有新增依賴。
- 初始測試先因功能缺失失敗，實作後通過；新增邊界與審查回歸測試亦先重現失敗。
- 最終 `.venv/Scripts/python.exe -m pytest -q --tb=short`：94 passed in 25.68s。
  Phase 5 新增 31 項測試，其餘 63 項為既有功能回歸。
- 覆蓋範圍：Decimal NaN／Infinity／負數／浮點拒絕、4.50 邊界、單次確認、
  參數／Key 更動、報價過期、並行保留、重啟與跨月保留、費用更正、
  執行中已核費請求仍攔截、提交逾時不重試、取消不清零、未知單位拒絕、
  安全主機、重新導向拒絕、Key 錯誤遮罩、CDN 無憑證、缺失帳單非零、
  真實零費用的匹配事件、GUI 否決／同意及不重用確認、Mock 離線。
- 獨立審查找到已核對帳單的後續跨月調整可能解除費用攔截。已以假 HTTP
  重現，加入獨立 billing_unresolved 欄位、保留既有金額與提交前再次攔截。
  回歸測試確認再查 COMPLETED 也不能解除費用待核對，全套通過。
- `.venv/Scripts/python.exe tests/smoke_phase5.py`：PASS。實際 Qt 視窗以假 Key、
  假 HTTP 走完報價、明確確認、單次假提交、查詢、候選預覽、帳單核對。
  所有 socket 連線封鎖；快照已目視檢查，並標明假資料與非真實 fal.ai 成果。
- compileall 通過；pip check：No broken requirements found。
- 沒有真實 Key、實際 WinVault 操作、真實推理／價格 API 請求或付費工作。
  官方資料僅透過公開文件查核；測試費率都是測試資料，不是正式價格。

## 尚未完成／未驗證

- 真實帳戶端到端連線、Key 權限、WinVault 保存、實際價格／單位回應及
  真實計費事件均尚未實機驗證；不能以離線測試宣稱雲端已成功生成。
- Phase 6：角色一致性與美術品質、長時間使用、Windows 打包仍未處理。
- 沒有自動輪詢、自動恢復提交、手動費用清零或多模型／Provider 實作。
- 沒有供應商帳單硬上限設定、自動購買 credits 或代為更改帳戶權限。

## 技術風險與決定

- 本機預算不是供應商硬上限，不能保證帳單永遠不超過 US$5；其他工具用量、
  價格變更、延遲／調整帳單、稅項及帳本刪除都不受此本機控制。
- 官方文件顯示價格可用一般 API 權限，逐筆帳單需額外讀取權限；權限不足
  保持未決並阻止新生成。使用者自行決定最小必要權限，程式不自動升權。
- 提交逾時且沒有供應商 ID 時，無法安全自動恢復或核費；保留並阻擋新請求，
  需供應商人工協助。本版不提供強制清零或不明費用豁免。
- 跨月調整、超過 90 天／20 頁或格式不明帳單，保留並要求人工核對；
  舊確認金額可見，但不是聲稱最新費用已完整結清。
- 256×256 以一整個 image／megapixel 單位保守估算，無法識別的單位拒絕；
  這不是供應商鎖價合約。真實服務若換欄位、CDN 主機或路由將停止而非繞過。
- HTTP 無強制中途終止，關閉視窗會等目前操作完成／逾時；大量帳單分頁可能較慢。
- 結果不保證透明、方向一致或可直接分層；另存 PNG 後仍需人工準備素材。
- 帳本與暫存測試資料分離；只有開啟 AI 工具才初始化正式本機帳本。
  現有工作目錄沒有 Git，未建立提交。

## 下一步建議

先檢視 AI 使用說明與離線流程，再規劃 Phase 6 的品質、錯誤提示、Windows 打包。
若要真人帳戶驗證，需另行安排，任何付費生圖仍須逐筆取得明確確認。
本輪不自動開啟真實驗證、使用 Key 或發出付費請求。

## 官方文件（2026-10-29 查核）

- [價格與單位](https://fal.ai/docs/platform-apis/v1/models/pricing)
- [認證與權限](https://fal.ai/docs/api-reference/platform-apis/authentication)
- [逐筆帳單事件](https://fal.ai/docs/platform-apis/v1/models/billing-events)
- [FLUX.1 Schnell 欄位](https://fal.ai/models/fal-ai/flux/schnell/api)
- [提交子路徑](https://fal.ai/docs/api-reference/inference-api/queue/submit-path)
- [取消](https://fal.ai/docs/api-reference/inference-api/queue/cancel)
- [付款條款](https://fal.ai/legal/terms-of-service)
