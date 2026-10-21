<p align="center">
  <img src="icon.png" width="128" alt="icon">
</p>

<h1 align="center">Limbus 自動戰鬥 ＆ 視窗自動按鍵器</h1>

<p align="center">
  Windows 小工具：看遊戲畫面自動幫你打 <b>Limbus Company</b> 的戰鬥，另附一個通用的「對指定視窗連續按鍵」工具。
</p>

> [!WARNING]
> 使用任何自動化工具都**可能違反遊戲的服務條款**，並有帳號被處分的風險。**請自行評估、自負風險**。使用前請先閱讀 [使用條款與免責聲明](DISCLAIMER.md)。
> 本專案與 Project Moon 無任何關係，也未獲其授權或認可。

---

## 目錄

- [功能](#功能)
- [下載與執行](#下載與執行)
- [Limbus 自動戰鬥 使用說明](#limbus-自動戰鬥-使用說明)
- [視窗自動按鍵器 使用說明](#視窗自動按鍵器-使用說明)
- [常見問題](#常見問題)
- [從原始碼執行 / 自行打包](#從原始碼執行--自行打包)
- [運作原理](#運作原理)
- [授權](#授權)

## 功能

### Limbus 自動戰鬥（`Limbus自動戰鬥.exe`）

| 遊戲畫面 | 程式動作 |
|---|---|
| 隊伍編成畫面 | （可選）按 Enter，沿用目前的隊伍開始戰鬥 |
| 輪到選技能 | 按 `P` + `Enter`（勝率自動配置 → 開始回合） |
| 戰鬥動畫中 | 不動作，等下一回合 |
| 戰鬥中跳出選項 / 事件 | 立刻暫停並播放提示音；你選完、回到戰鬥畫面後自動繼續 |
| 戰鬥畫面消失太久（例如打輸） | 暫停並播放提示音 |
| VICTORY | 播放勝利提示音，等下一場戰鬥再自動接手 |

- **背景執行**：遊戲視窗被其他視窗蓋住也能運作（不能最小化），送鍵預設不搶焦點。
- **不看文字**：只比對按鈕、圖示的形狀，**漢化包、英文、韓文介面都能用**。
- **支援不同解析度**：自動校準介面縮放倍率；真的認不到時可以用自己的畫面「重新取樣」。
- **提示音可自訂**：兩種提示音都能試聽、更換、開關。
- **快捷鍵**：`F8` 開始 / 停止，`Ctrl+Y` 暫停 / 繼續。

### 視窗自動按鍵器（`視窗自動按鍵器.exe`）

對任何指定的視窗，以固定間隔重複送出一串按鍵（例如 `p{ENTER}`），可以錄製按鍵、設定次數、背景或前景送鍵。

## 下載與執行

1. 到 [Releases](../../releases) 下載最新版的 `Limbus自動戰鬥.exe`（以及需要的話 `視窗自動按鍵器.exe`）。
2. 直接雙擊執行，**不需要安裝 Python**。第一次開啟需要幾秒鐘解壓縮。
3. Windows 可能跳出「Windows 已保護您的電腦」：點「**其他資訊** → **仍要執行**」。這是因為執行檔沒有付費的數位簽章，不是病毒；不放心的話可以[從原始碼執行](#從原始碼執行--自行打包)。

> 系統需求：Windows 10 / 11（64 位元）。

## Limbus 自動戰鬥 使用說明

### 快速開始

1. 開啟遊戲（建議**視窗模式或無邊框視窗**），開啟 `Limbus自動戰鬥.exe`。
2. 在遊戲裡進到**選技能的畫面**，按程式的「**測試辨識**」：紀錄應該顯示「選技能回合」，並完成自動校準。
3. 按「**開始**」或 `F8`，接下來程式會自己打。

### 設定說明

| 設定 | 說明 | 預設 |
|---|---|---|
| 隊伍畫面：自動按「開始戰鬥」 | 在隊伍編成畫面自動按 Enter 開戰（沿用目前選好的隊伍） | 關 |
| 選技能時按 | 輪到選技能時送出的按鍵，語法見[按鍵語法](#按鍵語法) | `p{ENTER}` |
| 每個鍵按多久 | 按下到放開的時間（毫秒）。遊戲偶爾沒反應可以調大 | 50 |
| 送鍵方式 | **背景傳送**：不搶焦點，可以同時做別的事<br>**前景模擬**：每次切到遊戲視窗再按，背景沒反應時用 | 背景傳送 |
| 戰鬥畫面消失 N 秒就提示 | 戰鬥中看不到戰鬥介面超過 N 秒（例如打輸）就暫停並提示。EGO 動畫約 15 秒，請保留餘裕 | 25 |
| 提示音 | 「輸了＆跳出選項」「戰鬥勝利」兩種，可試聽、更換、關閉 | 開 |

### 手動使用 EGO

選技能畫面一出現，程式就會立刻按下 `P` + `Enter`。想手動選 EGO 的回合，請**先按 `Ctrl+Y` 暫停**，選完、開始回合後再按 `Ctrl+Y` 繼續。
（程式按過之後若偵測到你在遊戲裡操作，不會再重按打斷你。）

### 解析度、校準與重新取樣

- **自動校準**：第一次看到戰鬥、選技能、選項或隊伍畫面時，程式會自動找出介面的縮放倍率，並依視窗尺寸記住。「辨識」那一列會顯示結果，例如 `1920×1057 → 1.00 倍`。換解析度後會自動重新校準；也可以按「**重新校準**」。
- **重新取樣**：如果某個畫面一直認不到（測試辨識的分數很低），切到那個遊戲畫面，按「**重新取樣…**」，選擇元素後用滑鼠框住它、按「儲存這個樣本」。框的位置要在黃色虛線範圍內。自訂樣本會優先使用；按「**恢復預設樣本**」可以改回內建的。

可以重新取樣的元素：

| 元素 | 位置 | 用途 |
|---|---|---|
| 齒輪按鈕 | 右上角 | 判斷「戰鬥中」 |
| `«` 按鈕 | 右上角 | 判斷「輪到選技能」 |
| VICTORY 字樣 | 畫面中央 | 判斷「勝利」 |
| 面板上方的吊鉤 | 左上方 | 判斷「跳出選項 / 事件」 |
| 開始戰鬥按鈕 | 右下角 | 判斷「隊伍編成畫面」 |

### 設定檔位置

設定、校準結果、自訂樣本都存在 `%APPDATA%\LimbusAutoBattle\`。刪掉這個資料夾就會回到初始狀態。

## 視窗自動按鍵器 使用說明

1. 從下拉選單選擇目標視窗（或按「3 秒後抓取前景視窗」再點一下目標視窗）。
2. 輸入按鍵序列，或按「**錄製按鍵**」直接在鍵盤上按。
3. 設定**每輪間隔（秒）**與**次數**（0 = 無限）。
4. 按「開始」或 `F8`；執行中按 `Ctrl+Y` 暫停。

| 模式 | 說明 |
|---|---|
| 背景傳送 – 送遊戲按鍵 | 給遊戲用，不搶焦點 |
| 背景傳送 – 送文字 | 給記事本、聊天框用，支援中文與大小寫 |
| 讓目標以為自己在前景 | Discord、瀏覽器、Unity 遊戲在背景時會忽略按鍵，需要勾選 |
| 前景模擬 | 每次切到目標視窗再按，相容性最高 |

### 按鍵語法

| 寫法 | 意思 |
|---|---|
| `p` | 按 P |
| `{ENTER}` `{TAB}` `{SPACE}` `{ESC}` `{BACKSPACE}` `{DELETE}` | 特殊鍵 |
| `{UP}` `{DOWN}` `{LEFT}` `{RIGHT}` `{HOME}` `{END}` `{PGUP}` `{PGDN}` | 方向 / 翻頁鍵 |
| `{F1}` ～ `{F24}` | 功能鍵 |
| `{WAIT 0.5}` | 暫停 0.5 秒 |
| `{LBRACE}` `{RBRACE}` | 大括號 `{` `}` |

範例：`p{ENTER}`、`hello{WAIT 1}{ENTER}`

## 常見問題

<details>
<summary><b>紀錄顯示「已送出按鍵」，但遊戲沒反應</b></summary>

把「送鍵方式」改成**前景模擬**，並把「每個鍵按多久」調到 50～100 毫秒。
</details>

<details>
<summary><b>「測試辨識」一直顯示「非戰鬥畫面」或分數很低</b></summary>

1. 確認遊戲沒有最小化。
2. 按「重新校準」後在選技能畫面再測一次。
3. 還是不行就用「重新取樣…」以你自己的畫面建立樣本。
</details>

<details>
<summary><b>EGO 或大招動畫時跳出警告</b></summary>

把「戰鬥畫面消失 N 秒就提示」調大（例如 35）。
</details>

<details>
<summary><b>F8 / Ctrl+Y 沒反應</b></summary>

快捷鍵被其他程式占用了（例如同時開著兩個本工具），程式紀錄會顯示「註冊失敗」。請關掉其他程式，或直接用按鈕操作。
</details>

<details>
<summary><b>防毒軟體說這是病毒</b></summary>

PyInstaller 打包、又會模擬按鍵的程式很常被誤判。原始碼完全公開，你可以自行檢查，或[從原始碼執行](#從原始碼執行--自行打包)。
</details>

<details>
<summary><b>遊戲是用系統管理員身分執行的</b></summary>

本工具也要「以系統管理員身分執行」，否則 Windows 會擋下按鍵。
</details>

## 從原始碼執行 / 自行打包

需要 Python 3.10 以上（開發時使用 3.14）。

```bash
pip install -r requirements.txt
python limbus_battle.pyw      # Limbus 自動戰鬥
python auto_key.pyw           # 視窗自動按鍵器
```

打包成 exe（輸出到 `dist\`）：雙擊 `build.bat`，或執行

```bash
python build.py
```

### 檔案結構

```
├─ limbus_battle.pyw     Limbus 自動戰鬥（畫面辨識、狀態判斷、GUI）
├─ auto_key.pyw          視窗自動按鍵器（GUI）
├─ keysender.py          共用：視窗列舉、按鍵語法、背景 / 前景送鍵
├─ limbus_templates/     辨識用的圖示樣本（*_mask.png 為遮罩，黑色部分不比對）
├─ sounds/               預設提示音
├─ icon.ico / icon.png   程式圖示
├─ build.py / build.bat  打包腳本
└─ requirements.txt
```

## 運作原理

1. 每 0.3 秒用 Windows 的 `PrintWindow` 擷取遊戲視窗（被遮住也拍得到）。
2. 把畫面縮放到 1920 寬，在固定區域（右上角、左上方、中央、右下角）用 OpenCV 模板比對找出特定圖示。
3. 依照「現在看到什麼」切換狀態（等待 → 戰鬥中 → 需要手動 → 勝利），決定要不要送鍵。
4. 送鍵預設用 `PostMessage` 直接送進遊戲視窗，不搶焦點；前景模式則用 `SendInput` 模擬實體鍵盤。

所有處理都在你的電腦上完成，**不會讀寫遊戲記憶體、不修改遊戲檔案、不連網**。

## 授權

- 程式碼：[MIT License](LICENSE)
- 程式圖示（`icon.png`、`icon.ico`）：原創作品，著作權屬於作者。
- `limbus_templates/` 內的圖片擷取自 Limbus Company 遊戲畫面，著作權屬於 Project Moon，僅作為畫面辨識用途，不在 MIT 授權範圍內。
- 使用前請閱讀 [使用條款與免責聲明](DISCLAIMER.md)。

---

<details>
<summary><b>English summary</b></summary>

**Limbus Auto Battle** is a Windows tool that watches the Limbus Company window and automates combat: it presses `P` + `Enter` whenever the skill-selection turn appears, can press Enter on the team-formation screen to start the battle, pauses with a sound alert when a mid-battle choice/event appears or the battle UI disappears (e.g. defeat), and plays a sound on VICTORY. Detection uses image template matching on icons only (no text), so it works with any language or fan translation, auto-calibrates to different resolutions, and lets you re-sample icons from your own screen. Hotkeys: `F8` start/stop, `Ctrl+Y` pause/resume.

**Window Key Sender** sends a key sequence (e.g. `p{ENTER}`) to any chosen window at a fixed interval, in the background or foreground.

Using automation tools may violate the game's Terms of Service — use at your own risk. Not affiliated with or endorsed by Project Moon. Code is MIT licensed; template images are cropped from the game and belong to Project Moon. See [DISCLAIMER.md](DISCLAIMER.md).
</details>
