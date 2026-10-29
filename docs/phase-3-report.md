# Phase 3 completion report — 2026-10-29

## 已完成功能

- 四方向六層模板：頭、軀幹、左右手、左右腿；明確的關節與繪製順序。
- JSON 模板載入、24 張圖片驗證、透明 RGBA、路徑限制與有界參數。
- 內建 CPU 測試人偶；examples/six-layer-demo 含完整 JSON 與 24 張 PNG。
- Pillow CPU 生成四方向各四幀，256×256 RGBA；固定腳底中心 Pivot。
- 可調手臂／腿部擺幅、身體起伏；超出畫布會提示裁切。
- 背景載入與生成、取消及過期結果拒絕，不使用 AI、GPU 或網路。
- 候選四方向預覽、實際計時播放、逐幀檢視及 FPS 控制。
- 明確確認後一次套用模板與 16 幀；失敗回復，不覆蓋原資料。
- schema 2 保存模板，讀取 schema 1 升級；另存時複製所有圖層與動畫素材。

## 修改的檔案

- 新增 core/rig.py；修改 core/models.py、project_repository.py、project_service.py。
- 新增 animation/templates.py、animation/walk.py。
- 新增 ui/preview.py、template_worker.py、template_dialog.py；修改 ui/main_window.py。
- 新增 tests/test_phase3.py、test_phase3_ui.py、smoke_phase3.py；修改 test_phase2.py。
- 新增 examples/six-layer-demo/template.json 及 layers/ 下 24 張 PNG。
- 更新 README.md、docs/architecture.md。
- 新增 docs/phase-3-plan.md、template-format.md、phase-3-preview.png、本報告。

## 測試方式與結果

- 環境：Windows、Python 3.12.14、PySide6 6.12.0、Pillow 13.0.0。
- 實作前核心測試 12 項因功能缺失失敗；GUI 測試 3 項因功能缺失失敗。
- 最終 `.venv/Scripts/python.exe -m pytest -q --tb=short`：47 passed in 21.76s。
- 範圍：六層與四方向、關節／參數邊界、路徑越界、透明背景、遺失素材、
  圖層順序、16 幀格式、可重現結果、取消、裁切警告、schema 1 相容、
  素材另存、部分寫入回復、候選不改原動畫、參數失效及實際計時預覽。
- `.venv/Scripts/python.exe tests/smoke_phase3.py`：PASS，實際 Qt 視窗完成
  載入、背景生成、四幀計時播放、四方向檢視、確認套用、保存與重開。
- 畫面快照已產生並目視檢查；pip check：No broken requirements found。
- 獨立審查找到匯入失敗後模板按鈕未恢復；已以失敗回歸測試重現並修復，
  全套測試再次通過。無其他重要審查發現。
- 沒有付費請求、真實 Key、AI 模型下載、GPU 或額外依賴安裝。

## 尚未完成事項

- Phase 4–6：Sprite Sheet／JSON／Unity 匯出、真實 fal.ai、憑證後端、
  持久化預算管理、一致性優化與 Windows 打包均未實作。
- 無自動拆圖、自動產生其他方向、圖形化關節編輯器或逆向運動學。
- 尚未全面手動測試 Windows 檔案對話框、高 DPI、多螢幕與長時間使用。

## 技術風險與實作決定

- 關節與順序透過文件化 JSON 編輯；若需圖形化編輯器，必須另列功能。
- 簡單剛性旋轉不能保證落腳固定、接縫無縫或正式美術品質；需人工檢視。
- 測試人偶是幾何示意素材，不是日系動漫成品；正式效果需合適分層美術。
- 超出畫布採警告與裁切，不自動修正；第 1、3 幀通過姿勢重複。
- 舊素材保留以保護已儲存草稿；反覆套用增加磁碟使用，崩潰可能留孤立檔。
- 圖片解碼與合成在背景；小型素材寫入與另存複製仍同步執行。
- 專案保存會升級為 schema 2，舊版應用無法讀取新格式。
- 工作目錄仍無 Git 儲存庫，未建立提交。

## 下一步建議

先試用自己的六層素材並評估接縫、腳滑與遮擋順序；確認 Phase 3 後，
另行規劃 Phase 4 的獨立 PNG、1024×1024 Sprite Sheet、JSON 與 Unity 匯出。
不得自動開始 Phase 4。
