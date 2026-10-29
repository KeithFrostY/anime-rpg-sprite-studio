# Windows 免安裝測試版

## 使用

解壓 `AnimeRpgSpriteStudio-0.6.0-windows-test.zip`，執行資料夾中的
`AnimeRpgSpriteStudio.exe`。保留整個 `_internal`，不能只移動 EXE。
不需另裝 Python；請把自己的專案放在可寫入的個人資料夾。
此包未簽章，供內部驗收。主視窗「說明 → 快速開始」可查看操作步驟。

離線可進行角色編輯、PNG 匯入、四方向預覽、CPU 分層動畫、一致性檢查與匯出。
前後幀疊影及腳底線只是顯示輔助，不會寫入 PNG。
一致性檢查以非零 alpha 的輪廓邊界為準，提示全透明、完全不透明、觸邊、
水平中心偏離超過 32 px、底部距離超過 16 px、同方向中心／底部變動超過
6 px 或寬高變動超過 12 px。合理的擺動、武器與披風也可能觸發警告，
工具不能判斷人物身份或保證落腳品質，不會自動修正原圖。

AI 預設 Mock。fal.ai 仍需自己設定 Key、取得最新報價、逐筆確認付費；
本次打包驗收沒有真實 Key、憑證讀寫或付費請求。

## 建置

需要 Windows、Python 3.12 與此專案環境：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test,build]"
.\.venv\Scripts\python.exe tools/build_windows.py
```

每次建立獨立的 build／dist 時間戳資料夾，不刪除舊包。
最新路徑與 SHA-256 記錄在 `build/latest-release.json`。
建置只包含指定文件、24 張範例圖、所需模組、Qt 外掛與授權原附文件；
不包含帳本、Key、測試目錄、虛擬環境或個人專案。

建置程序隔離 PATH，避免其他工具的同名 DLL 混入。實測曾因主機 Poppler
的 ICU78 別名取代 Windows ICU 而無法匯入 QtWidgets；隔離後已通過 EXE 驗收。
不要手動將其他軟體的 DLL 複製到 `_internal` 來修補版本問題。

## 可重跑離線驗收

```powershell
.\AnimeRpgSpriteStudio.exe --self-test-report C:\你的測試資料夾\result.json
```

這是明確選用的自我驗收入口，正常啟動不執行。它封鎖 Python TCP、DNS、
UDP 傳送與真實 WinVault 方法，使用暫存專案、測試模板與假憑證介面。
實際驗證：GUI、中文路徑、24 層素材、16 幀生成與套用、儲存重開、計時播放、
疊影基準線、一致性檢查、PNG／Sheet／JSON 匯出、Mock、SQLite 與後端模組匯入。
驗收只在指定位置留下 JSON 報告；選用 `--self-test-screenshot 路徑.png` 可存畫面。
不會測試真實 Key 或新增付費請求。

## 驗證邊界與授權

已在目前 Windows 主機的獨立 EXE 執行，工作目錄位於原始碼以外的驗收資料夾；
不是乾淨 VM 驗證，也未宣稱涵蓋所有 Windows 10/11 版本、多螢幕或 DPI 組合。
尚未完成真實 WinVault 操作、實際 fal.ai 生圖、長時間 soak、簽章或安裝器。

套件保留已安裝依賴的原附授權文字。此環境 PySide6/Shiboken 的原附文件
僅有商業授權條文，尚未確認公開散布權；本包是內部測試成果，公開發佈前
需核對套件來源及適用授權，不能由本建置推論合規或已取得商業授權。
[Qt 官方授權資訊](https://doc.qt.io/qt-6/licensing.html)、
[Qt for Python](https://doc.qt.io/qtforpython-6/)。

本專案未購買服務、簽章或授權，也沒有對外發布此包。
