# 協同安全顧問公司｜Synergy Safety Consultant Company

此儲存庫為 **協同安全顧問公司** 的官方靜態網站，部署於 GitHub Pages。

## 內容（Phase 1）

- 語言：**繁體中文**（`zh-Hant-HK`），並附英文公司名稱與服務標題
- 首頁：`index.html`、`styles.css`、`assets/site.js`
- **職安資訊**：`news.html`（新聞）、`analysis.html`（意外分析）、`stats.html`（統計儀表板）、`alerts.html`（勞工處警示索引）
- 法務：`disclaimer.html`（全站頁尾連結）
- 資料：`data/news.json`、`data/analyses.json`、`data/alerts.json`、`data/stats.json`、`data/form2-accident-types.json`（表格2第K部官方類別用字）
- 品牌標誌：`assets/logo.png`；新聞圖片可放 `assets/news/`；個案 PDF 在 `assets/reports/`

### `data/news.json`

每個 `items[]` 物件欄位：

| 欄位 | 說明 |
|------|------|
| `id` | 穩定識別碼（建議 `YYYY-MM-DD-slug`） |
| `publishedAt` | 收錄／發布時間（ISO 8601） |
| `severity` | `fatal` 或 `non_fatal` |
| `title`, `location`, `occurredAt`, `summary` | 報導摘要 |
| **`accidentType`** | **意外類別（對照表格2第K部）**，見下表 |
| `contractor`, `contractorConfidence` | 承建商（若有） |
| `sources[]` | `{ outlet, url }` |
| `image` | 選填，相對路徑 |

#### `accidentType`（勞工處表格2 Rev.17 第K部 — 單選）

官方類別名錄見 `data/form2-accident-types.json`；中文 PDF：<https://www.labour.gov.hk/common/form/ecd/pdf/f2_c.pdf>。

```json
"accidentType": {
  "code": "12",
  "label": "遭移動中的車輛撞倒"
}
```

- **`code`**：字串 `"01"`–`"17"`（與表格2剔號一致）
- **`label`**：必須使用官方中文名稱（與上列名錄一致，勿改寫）
- **`fallDistanceMetres`**（選填）：僅當 `code` 為 `"04"` 且報導有墮下距離時填寫（數字，單位：米）
- **`otherSpecify`**（選填）：僅當 `code` 為 `"17"` 時填寫簡短說明

歸類由站方依公開報導對照表格2，**並非**勞工處或僱主呈報之官方定性。

### `data/analyses.json`

`schemaVersion`: **2** — 每則新聞一份公開資料分析報告（非官方調查）。

每個 `items[]` 主要欄位：`id`, `newsId`, `reportNo`, `title`, `publishedAt`, `writtenAt`, `hazardTags[]`, `lead`（列表摘要）, `reportNotice`（報告置頂聲明）, `sections[]`（十個章節：`heading`、可含 `rows`、`paragraphs`、`bullets`、`timeline`、`subsections`、`legalTiers`、`legalRefs`、`refs`）。

`相關法例及守則` 建議使用 `legalTiers[]` 三層結構：`tierLabel` ＋ `refs[]`（`title`, `provision`, `url`, `applicability`, `relevance`）；每條須為可核對之官方文件連結，並標示【可能適用】及與個案之相關說明。

已有對應新聞的分析另設 `pdf`（相對路徑，例如 `assets/reports/SSC-2026-AR-011.pdf`）。`news.html` 在「閱讀意外分析」旁、`analysis.html` 在報告卡片上，只在該欄有值時顯示「下載 PDF」。沒有分析的新聞不產生 PDF，也不顯示下載按鈕。

更新或新增分析後，於儲存庫根目錄重新產生 PDF，並把產出的 PDF 一併提交：

```bash
python3 -m pip install reportlab pillow fonttools
python3 scripts/build-report-pdfs.py
```

首次執行會下載 Noto Sans TC 到 `scripts/.font-cache/`（不入庫），再把子集嵌入各 PDF。分析正文照 `analyses.json` 原文輸出；新聞摘要照 `news.json`，但會略去「姓X」形式的傷者姓氏。

舊版 `causes` / `lessons` / `legalRefs` / `summary` 仍可由 `analysis.html` 後備顯示，但新稿請使用 `sections`。

### `data/alerts.json`

每個 `items[]`：`title`, `publishedAt`, `summary`, `category`, `officialUrl`；頂層 `landingUrl` 為勞工處職安警示主頁。本站僅摘要並連結官方，不重刊全文。

### `data/stats.json`

由 `data/news.json` 匯總（自 **2026 年 10 月**起）：總數、致命／非致命、按月、地區（標題／地點關鍵字推斷）及 **`byAccidentType`**（各則新聞之 `accidentType` 計數）。更新新聞後可執行：

```bash
python3 scripts/build-stats.py
```

`stats.html` 會優先讀取此檔；若缺失則於頁面內從 `news.json` 即時計算。數字及意外類別分佈僅代表本站公開收錄，**並非**勞工處官方統計。

## 本地預覽

```bash
python3 -m http.server 8080
```

於瀏覽器開啟 `http://localhost:8080/`。

## GitHub Pages

**Settings → Pages → Deploy from a branch**，來源 **`main`**、資料夾 **`/ (root)`**（已含 `.nojekyll`）。

公開網址（組織 `synergy-safety`）：

| 頁面 | URL |
|------|-----|
| 首頁 | https://synergy-safety.github.io/synergy-safety/ |
| 新聞 | https://synergy-safety.github.io/synergy-safety/news.html |
| 意外分析 | https://synergy-safety.github.io/synergy-safety/analysis.html |
| 統計 | https://synergy-safety.github.io/synergy-safety/stats.html |
| 勞工處警示 | https://synergy-safety.github.io/synergy-safety/alerts.html |
| 免責聲明 | https://synergy-safety.github.io/synergy-safety/disclaimer.html |

若儲存庫為 **Private**，需改為 **Public** 或啟用支援私人 Pages 的方案後，方可在上述網址存取。
