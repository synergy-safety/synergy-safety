# 協同安全顧問公司｜Synergy Safety Consultant Company

此儲存庫為 **協同安全顧問公司** 的官方靜態網站，部署於 GitHub Pages。

## 內容（Phase 1）

- 語言：**繁體中文**（`zh-Hant-HK`），並附英文公司名稱與服務標題
- 首頁：`index.html`、`styles.css`、`assets/site.js`
- **職安資訊**：`news.html`（新聞）、`analysis.html`（意外分析）、`stats.html`（統計儀表板）、`alerts.html`（勞工處警示索引）
- 法務：`disclaimer.html`（全站頁尾連結）
- 資料：`data/news.json`、`data/analyses.json`、`data/alerts.json`、`data/stats.json`
- 品牌標誌：`assets/logo.png`；新聞圖片可放 `assets/news/`

### `data/news.json`

每個 `items[]` 物件欄位：`id`, `publishedAt`, `severity`, `title`, `location`, `occurredAt`, `summary`, `contractor`, `contractorConfidence`, `sources[]`, `image`（選填）。

### `data/analyses.json`

每個 `items[]`：`id`, `newsId`（選填）, `title`, `publishedAt`, `hazardTags[]`, `causes[]`, `legalRefs[{title,url}]`, `lessons[]`, `summary`。

### `data/alerts.json`

每個 `items[]`：`title`, `publishedAt`, `summary`, `category`, `officialUrl`；頂層 `landingUrl` 為勞工處職安警示主頁。本站僅摘要並連結官方，不重刊全文。

### `data/stats.json`

由 `data/news.json` 匯總（自 **2026 年 10 月**起）：總數、致命／非致命、按月、地區及危害類型（部分為標題／地點關鍵字推斷）。更新新聞後可執行：

```bash
python3 scripts/build-stats.py
```

`stats.html` 會優先讀取此檔；若缺失則於頁面內從 `news.json` 即時計算。數字僅代表本站公開收錄，**並非**勞工處官方統計。

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
