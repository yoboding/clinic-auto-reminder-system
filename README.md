# 診所智慧自動化回診提醒與預約狀態管理系統
*(Clinic Auto-Reminder & Status Sync Engine)*

本專案旨在解決診所櫃檯同仁每日需人工對表、發送回診提醒訊息的耗時痛點。透過 Python 結合雲端 API 與背景定時排程，實現零人工干預的定時提醒發送與預約狀態同步更新閉環。

---

## 💡 解決的商業痛點 (Problem & Business Impact)

* **診所痛點**：
  * 櫃檯人員每日需花費 1–2 小時手動搜尋明日預約病患、逐一發送提醒訊息，過程重複且容易遺漏或填錯。
  * 提醒發送後無法即時自動更新預約狀態，易造成重複提醒或同仁資訊不對稱。
* **解決方案效益**：
  * **行政人力節省 100%**：自動化掃描預約資料並產出動態提醒內容。
  * **跨系統資料狀態閉環**：發送後自動回寫雲端資料庫，確保狀態實時同步，消除重覆發送風險。

---

## 🏗️ 系統架構圖 (System Architecture)

```text
[ 診所預約資料庫 (Google Sheet) ]
            │
            ▼ (1. 每日 19:00 背景定時觸發)
[ 排程引擎 (Cron Task Manager) ]
            │
            ▼ (2. 讀取與時間條件過濾：明日預約 & '待提醒')
[ Python 自動化核心模組 (OAuth 2.0 / Google Sheets API) ]
            │
            ├──────► (3. 訊息生成與發送) ──► [ 擬真通知 / LINE Messaging API ]
            │
            └──────► (4. 狀態閉環同步) ────────► [ 雲端資料庫 Status 更新為 '已發送提醒' ]

```

## 🛠️ 技術棧 (Tech Stack) ##
核心開發語言：Python 3
雲端 API 串接：Google Sheets API v4, Google Drive API (Google API Python Client)
資安與驗證：OAuth 2.0 Client Credentials Authentication & Token Auto-refresh Flow (token.json)
排程與自動化維運：Shell Scripting (run.sh), Cron Task Scheduler (crontab)

## ✨ 專案亮點與工程實踐 (Highlights) ##
OAuth 2.0 安全驗證與 Token 持久化：
實作完整 OAuth 2.0 授權機制，首次登入存取權限後產出本地 token.json，讓後續定時任務能無感自動連線備份。
條件過濾與狀態回寫閉環：
動態計算次日日期 (YYYY-MM-DD)，精準鎖定 Status = '待提醒' 病患，處理完成即時將狀態覆寫為 '已發送提醒'。
無人值守定時維運機制：
撰寫專用 Shell 腳本封裝執行環境，結合 Cron 設定每日 19:00 背景觸發，並整合 cron_log.txt 提供即時執行日誌追蹤。
