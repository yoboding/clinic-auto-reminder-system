#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
診所自動化回診提醒系統 (reminder_system.py)
=================================================
功能簡述：
1. 使用 OAuth 2.0 桌面應用程式流程連接 Google Sheets API
2. 讀取「診所預約資料庫」試算表中的 Appointments 工作表
3. 找出「明天」且狀態為「待提醒」的預約紀錄
4. 模擬發送 LINE 提醒訊息 (印在 Terminal)
5. 將已發送提醒的紀錄狀態更新為「已發送提醒」

事前準備：
1. 到 Google Cloud Console 建立專案，啟用 Google Sheets API 與 Google Drive API
2. 建立「OAuth 用戶端 ID」(應用程式類型選擇「電腦版應用程式」)
3. 下載該憑證 JSON 檔案，重新命名為 credentials.json，放在與本腳本相同目錄下
4. 在 Google Sheets 中建立試算表，名稱為「診所預約資料庫」，並建立工作表
   「Appointments」，欄位（第一列標題）建議如下：
   PatientName | AppointmentDate | AppointmentTime | Notes | Status
   其中 AppointmentDate 格式請填 YYYY-MM-DD (例如 2026-08-07)
   Status 欄位初始值請填「待提醒」
"""

import os
import sys
import datetime

# Google API 相關套件
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 基本設定區
# ============================================================

# 存取範圍 (Scope)：
# spreadsheets -> 讀寫試算表內容
# drive        -> 讓程式能透過檔案名稱搜尋到試算表 (open() 需要用到 Drive API)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# 憑證檔案路徑 (與本腳本放在同一個目錄)
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# 試算表與工作表名稱
SPREADSHEET_NAME = '診所預約資料庫'
WORKSHEET_NAME = 'Appointments'

# 診所名稱 (可自行修改，會顯示在提醒訊息中)
CLINIC_NAME = 'XX診所'

# 欄位名稱常數，方便維護 (必須與 Google Sheets 標題列名稱完全一致)
COL_PATIENT_NAME = 'PatientName'
COL_APPOINTMENT_DATE = 'AppointmentDate'
COL_APPOINTMENT_TIME = 'AppointmentTime'
COL_NOTES = 'Notes'
COL_STATUS = 'Status'

# 狀態常數
STATUS_PENDING = '待提醒'
STATUS_SENT = '已發送提醒'


# ============================================================
# 認證流程
# ============================================================
def get_credentials():
    """
    取得 Google API 的授權憑證 (OAuth 2.0 桌面應用程式流程)。

    流程說明：
    1. 若同目錄下已存在 token.json，且憑證仍有效，直接讀取使用。
    2. 若 token 過期但有 refresh_token，則自動刷新，不需要重新登入。
    3. 若都沒有，則會開啟預設瀏覽器，導向 Google 登入/授權頁面，
       使用者同意授權後，程式會將取得的憑證寫入 token.json，
       供下次執行時直接使用，不需要每次都重新登入。

    Returns:
        Credentials: 已驗證的 Google API 憑證物件
    """
    creds = None

    # 步驟 1：檢查是否已經有先前儲存的 token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 步驟 2：如果沒有憑證，或憑證無效，則需要重新登入或刷新
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # token 過期但可以用 refresh_token 自動刷新，不需使用者互動
            print('🔄 憑證已過期，正在自動刷新 Token...')
            creds.refresh(Request())
        else:
            # 完全沒有憑證，或憑證無法刷新 -> 需要開啟瀏覽器重新授權
            if not os.path.exists(CREDENTIALS_FILE):
                print(f'❌ 找不到 {CREDENTIALS_FILE}，請先至 Google Cloud Console '
                      f'下載 OAuth 用戶端憑證，並放置於本程式同目錄下。')
                sys.exit(1)

            print('🌐 首次執行或憑證失效，即將開啟瀏覽器進行 Google 帳號授權...')
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            # run_local_server 會自動開啟預設瀏覽器，讓使用者登入並同意授權
            creds = flow.run_local_server(port=0)

        # 步驟 3：將取得的憑證（含 refresh_token）寫入 token.json，供下次直接使用
        with open(TOKEN_FILE, 'w', encoding='utf-8') as token_file:
            token_file.write(creds.to_json())
        print(f'✅ 已將授權憑證儲存至 {TOKEN_FILE}')

    return creds


# ============================================================
# Google Sheets 存取相關函式
# ============================================================
def open_worksheet(creds):
    """
    使用已驗證的憑證，透過 Google Drive API 搜尋試算表，
    並回傳 Google Sheets API 的 service 物件與該試算表的 spreadsheetId。

    這裡不使用 gspread 套件，而是直接使用 Google 官方的
    google-api-python-client，以完整展示底層 API 呼叫方式。

    Args:
        creds (Credentials): 已驗證的憑證

    Returns:
        tuple: (sheets_service, spreadsheet_id)
    """
    # 建立 Drive API service，用來依「檔案名稱」搜尋試算表 ID
    drive_service = build('drive', 'v3', credentials=creds)

    query = (
        f"name = '{SPREADSHEET_NAME}' "
        f"and mimeType = 'application/vnd.google-apps.spreadsheet' "
        f"and trashed = false"
    )
    results = drive_service.files().list(
        q=query, spaces='drive', fields='files(id, name)'
    ).execute()
    files = results.get('files', [])

    if not files:
        print(f'❌ 找不到名為「{SPREADSHEET_NAME}」的 Google 試算表，'
              f'請確認名稱是否正確，或該試算表是否已與此 Google 帳號共用/建立。')
        sys.exit(1)

    spreadsheet_id = files[0]['id']
    print(f'✅ 已找到試算表「{SPREADSHEET_NAME}」(ID: {spreadsheet_id})')

    # 建立 Sheets API service，用來讀寫該試算表內容
    sheets_service = build('sheets', 'v4', credentials=creds)

    return sheets_service, spreadsheet_id


def read_appointments(sheets_service, spreadsheet_id):
    """
    讀取 Appointments 工作表的所有資料 (包含標題列)。

    Returns:
        list[list[str]]: 二維陣列，第一列為標題列，之後每列為一筆預約紀錄
    """
    range_name = f'{WORKSHEET_NAME}!A:Z'  # 讀取整個工作表 (A 到 Z 欄，足夠應付大部分情況)

    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()

    values = result.get('values', [])

    if not values:
        print(f'⚠️ 工作表「{WORKSHEET_NAME}」目前沒有任何資料。')

    return values


def update_status_to_sent(sheets_service, spreadsheet_id, row_number, status_col_letter):
    """
    將指定列 (row_number) 的 Status 欄位更新為「已發送提醒」。

    Args:
        sheets_service: Google Sheets API service 物件
        spreadsheet_id (str): 試算表 ID
        row_number (int): 該筆紀錄在 Google Sheets 中的實際列號 (從 1 開始，含標題列)
        status_col_letter (str): Status 欄位對應的欄位字母 (例如 'E')
    """
    cell_range = f'{WORKSHEET_NAME}!{status_col_letter}{row_number}'

    body = {
        'values': [[STATUS_SENT]]
    }

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=cell_range,
        valueInputOption='RAW',
        body=body
    ).execute()


def column_index_to_letter(index):
    """
    將 0-based 欄位索引轉換為 Google Sheets 欄位字母 (0 -> A, 1 -> B, 25 -> Z, 26 -> AA ...)。

    Args:
        index (int): 0-based 欄位索引

    Returns:
        str: 對應的欄位字母
    """
    letter = ''
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


# ============================================================
# 核心商業邏輯
# ============================================================
def get_tomorrow_date_str():
    """
    取得電腦系統當前日期的「明天」日期字串。

    Returns:
        str: 格式為 YYYY-MM-DD 的明天日期
    """
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    return tomorrow.strftime('%Y-%m-%d')


def build_line_message(patient_name, appointment_date, appointment_time, notes):
    """
    組合擬真的 LINE 提醒訊息內容。

    Returns:
        str: 完整的提醒訊息文字
    """
    message = (
        f'---\n'
        f'【{CLINIC_NAME} 回診提醒】\n'
        f'{patient_name} 您好，提醒您預約了明天 ({appointment_date}) '
        f'{appointment_time} 的診次 ({notes})。\n'
        f'請確認是否能準時出席？\n'
        f'---'
    )
    return message


def process_reminders(sheets_service, spreadsheet_id):
    """
    主要處理流程：
    1. 讀取所有預約資料
    2. 篩選出「明天」且「待提醒」的紀錄
    3. 針對每筆符合條件的紀錄，印出提醒訊息並更新狀態

    Args:
        sheets_service: Google Sheets API service 物件
        spreadsheet_id (str): 試算表 ID
    """
    all_values = read_appointments(sheets_service, spreadsheet_id)

    if not all_values or len(all_values) < 2:
        print('目前沒有可處理的預約資料。')
        return

    header = all_values[0]
    data_rows = all_values[1:]

    # 檢查必要欄位是否存在
    required_columns = [
        COL_PATIENT_NAME, COL_APPOINTMENT_DATE,
        COL_APPOINTMENT_TIME, COL_NOTES, COL_STATUS
    ]
    for col in required_columns:
        if col not in header:
            print(f'❌ 工作表標題列缺少必要欄位「{col}」，請確認欄位名稱是否正確。')
            sys.exit(1)

    # 取得各欄位在標題列中的索引位置 (0-based)
    idx_patient_name = header.index(COL_PATIENT_NAME)
    idx_appointment_date = header.index(COL_APPOINTMENT_DATE)
    idx_appointment_time = header.index(COL_APPOINTMENT_TIME)
    idx_notes = header.index(COL_NOTES)
    idx_status = header.index(COL_STATUS)

    # Status 欄位對應的欄位字母 (用於後續更新儲存格)
    status_col_letter = column_index_to_letter(idx_status)

    tomorrow_str = get_tomorrow_date_str()
    print(f'📅 今日日期系統偵測完成，明天日期為：{tomorrow_str}')
    print(f'🔍 開始掃描符合條件（明天回診 且 狀態為「{STATUS_PENDING}」）的紀錄...\n')

    matched_count = 0

    # 逐列檢查資料
    # row_number 從 2 開始，因為第 1 列是標題列，Google Sheets 列號從 1 起算
    for offset, row in enumerate(data_rows):
        row_number = offset + 2

        # 由於 Google Sheets API 回傳的資料，若該列後面的欄位是空白，
        # 陣列長度可能會比標題列短，這裡用安全取值的方式避免 IndexError
        def safe_get(row_data, idx):
            return row_data[idx] if idx < len(row_data) else ''

        appointment_date = safe_get(row, idx_appointment_date).strip()
        status = safe_get(row, idx_status).strip()

        # 篩選條件：AppointmentDate 為明天 且 Status 為「待提醒」
        if appointment_date == tomorrow_str and status == STATUS_PENDING:
            patient_name = safe_get(row, idx_patient_name).strip()
            appointment_time = safe_get(row, idx_appointment_time).strip()
            notes = safe_get(row, idx_notes).strip()

            # 印出模擬的 LINE 提醒訊息
            message = build_line_message(
                patient_name, appointment_date, appointment_time, notes
            )
            print(message)
            print()  # 換行，讓多筆訊息之間有間隔

            # 更新該筆紀錄的 Status 欄位為「已發送提醒」
            try:
                update_status_to_sent(
                    sheets_service, spreadsheet_id, row_number, status_col_letter
                )
                print(f'✅ 已將 {patient_name} 的狀態更新為「{STATUS_SENT}」 '
                      f'(第 {row_number} 列)\n')
            except HttpError as e:
                print(f'❌ 更新第 {row_number} 列狀態時發生錯誤：{e}\n')

            matched_count += 1

    if matched_count == 0:
        print(f'目前沒有符合條件（{tomorrow_str} 且狀態為「{STATUS_PENDING}」）的預約紀錄。')
    else:
        print(f'🎉 本次共處理 {matched_count} 筆提醒通知。')


# ============================================================
# 程式進入點
# ============================================================
def main():
    print('=' * 50)
    print('診所自動化回診提醒系統 啟動中...')
    print('=' * 50)

    # 1. 取得 Google API 認證
    creds = get_credentials()

    # 2. 開啟目標試算表
    sheets_service, spreadsheet_id = open_worksheet(creds)

    # 3. 掃描明日待提醒資料，發送提醒並更新狀態
    process_reminders(sheets_service, spreadsheet_id)

    print('=' * 50)
    print('程式執行完畢。')
    print('=' * 50)


if __name__ == '__main__':
    main()
