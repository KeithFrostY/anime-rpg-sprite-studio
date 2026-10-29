# Phase 6 completion report — 2026-10-29

## 已完成功能

- 16 幀 CPU 輪廓一致性檢查：空白、完全不透明、觸邊、中心偏移、腳底距離、
  同方向中心／底部與尺寸變動。只提示，不修改美術或保證身份一致。
- 主視窗與候選視窗的腳底基準線、前後幀疊影；只影響顯示，不改 PNG。
- 背景品質檢查視窗、關閉／取消清理與固定通用錯誤提示，避免顯示秘密內容。
- 程式內快速開始文件、可定位的打包範例與文件資源。
- PyInstaller 0.6.0 Windows onedir 免安裝測試包，含 Qt 外掛、Pillow、
  Windows keyring 模組、24 層模板、使用文件及原附授權資料。
- 明確選用的離線自我驗收入口，封鎖 Python TCP／DNS／UDP 與真實憑證方法。
- ZIP、SHA-256 與建置清單；未建立安裝器、Unity 或對外發布服務。

## 交付檔案（僅此最終包通過驗收）

- ZIP：`dist/20261029-132924-953507/AnimeRpgSpriteStudio-0.6.0-windows-test.zip`
- EXE：`dist/20261029-132924-953507/AnimeRpgSpriteStudio/AnimeRpgSpriteStudio.exe`
- ZIP 大小：58,179,783 bytes。
- SHA-256：`eecbd0d4227ab1f2e7de9afc9078b1f4d15262a0135639f62294922a39a03d20`
- 校驗檔：同 ZIP 位置的 `.zip.sha256`。
- 驗收：`docs/phase-6-packaged-selftest.json`（passed=true、frozen=true）。
- 實際 EXE 畫面：`docs/phase-6-packaged-preview.png`。

解壓後執行 EXE，保留完整 `_internal`，不能只複製 EXE。
較早 dist 建置是診斷用失敗版本，不作為交付；未刪除或覆蓋它們。

## 修改的檔案

- 新增 animation/quality.py、ui/quality_dialog.py、runtime.py、selftest.py。
- 修改 ui/preview.py、main_window.py、template_dialog.py、bootstrap.py。
- 新增 packaging/entrypoint.py、AnimeRpgSpriteStudio.spec、tools/build_windows.py。
- 新增 tests/test_phase6.py；加強 tests/conftest.py 的 DNS／UDP／真實憑證封鎖。
- pyproject.toml：版本 0.6.0，PyInstaller 為 build-only 依賴。
- requirements-dev.lock.txt、README.md、docs/architecture.md。
- 新增 docs/phase-6-plan.md、quickstart.txt、release-notes.md、windows-release.md、
  phase-6-source-selftest.json、phase-6-packaged-selftest.json、兩張驗收 PNG、本報告。
- ignored build/、dist/ 下產生建置紀錄、免安裝資料夾、ZIP 與校驗檔。

## 測試方式與結果

- Windows x64、Python 3.12.14、PySide6 6.12.0、Pillow 13.0.0、PyInstaller 6.22.3。
- 先寫測試並觀察缺失功能失敗；新增 8 項 Phase 6 測試。
- 完整 pytest：102 passed in 25.83s。包括前 94 項回歸、實際 QWidget 像素
  比對確保疊影不改原圖、背景品質檢查與反覆關窗停止計時器。
- 獨立審查指出離線 guard 未封鎖 DNS／UDP；以假 resolver／sendto 重現失敗，
  修復後回歸通過。全套測試的隔離也一併加強；沒有真實 DNS 或 UDP 呼叫。
- 原始碼自我驗收通過：`python -m anime_rpg_sprite_studio --self-test-report ...`。
- 第一輪打包可建置，但 EXE 驗收失敗：QtWidgets 缺少 DLL 程序。
  擷取啟動錯誤、分析 PE 匯入與實際載入模組後，確認主機 Poppler ICU78 別名
  汙染打包搜尋路徑，與 Qt 使用的 Windows ICU ABI 不符。
  隔離建置 PATH 後重建，未盲目替換系統 DLL。
- 最終 EXE 從另一個工作目錄啟動，結束碼 0，frozen=true 自我驗收通過：
  GUI、中文路徑專案保存、24 層範例、CPU 16 幀生成／套用／重開、實際計時播放、
  疊影與基準線、背景品質檢查、18 檔完整匯出、Mock、SQLite、後端模組匯入。
- 自我驗收使用暫存專案與假憑證介面，沒有真實 API、Key 或 WinVault 操作。
- 實際打包畫面已目視檢查。ZIP testzip 通過，368 個 archive entries；
  檢查含 24 張範例圖與 qwindows.dll，不含帳本、測試、.venv 或不相容 ICU 別名。
- ZIP SHA-256 與清單一致；compileall／pip check 通過。

## 尚未完成事項

- 乾淨 Windows 10／11 VM、多機／多螢幕／各 DPI 組合的驗證。
- 長時間 soak、正式美術品質與 AI 四方向身份一致性保證。
- 真實 Key、實際 WinVault 讀寫、真實 fal.ai 生圖與帳單驗收。
- 程式簽章、安裝器、自動更新、公開發佈與發佈授權核實。

## 技術風險與決定

- 本版是未簽章的內部測試包。PySide6／Shiboken 原附授權文件只含商業條文，
  已如實保留；尚未確認公開散布權，公開發佈前需核對來源與適用授權。
  不宣稱本包完成法律合規，也未代為購買授權。
- onedir 保留可見 DLL／資源，易於驗證；代價是必須保留整個資料夾。
- 品質指標是固定閾值的輪廓檢查，可能把合理動作、武器或披風列為警告；
  無自動修圖，不可據此保證無腳滑、無接縫或人物一致。
- 打包依賴 Windows 系統 ICU 與支援的 Windows API；本機成功不是所有
  Windows 10/11 組合的證明。隔離 PATH 避免混入其他工具的同名程式庫。
- 離線自我驗收是 Python 呼叫層的封鎖，不是作業系統防火牆或封包監控。
  正常模式的付費功能仍需即時報價與逐筆確認，預算不是供應商硬上限。
- 工作目錄沒有 Git；未建立提交。較早失敗包保留供診斷，只提供最終驗證包。

## 下一步建議

先解壓最終包，以自己的素材試用並回報接縫／腳滑、視窗或匯出問題。
正式公開發佈前，另行完成乾淨 Windows 測試、Qt 發行來源／授權核對與簽章。
真實 API 驗收不是本階段自動後續步驟，任何付費仍需明確單次確認。
