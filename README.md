# 協同安全顧問公司｜Synergy Safety Consultant Company

此儲存庫為 **協同安全顧問公司** 的官方靜態落地頁，部署於 GitHub Pages。

## 內容

- 語言：**繁體中文**（`zh-Hant-HK`），並附英文公司名稱與服務標題
- 根目錄：`index.html`、`news.html`、`styles.css`
- 新聞資料：`data/news.json`（頁面 [`news.html`](news.html) 以 JavaScript 載入並渲染）
- 品牌標誌：`assets/logo.png`；新聞圖片可放 `assets/news/`

### `data/news.json` 項目結構

每個 `items[]` 物件欄位：

| 欄位 | 說明 |
|------|------|
| `id` | 唯一識別字串 |
| `publishedAt` | 刊登／更新日期（ISO 8601） |
| `severity` | `"fatal"` 或 `"non-fatal"` |
| `title` | 標題 |
| `location` | 地點（選填） |
| `occurredAt` | 事發日期（選填，ISO 8601） |
| `summary` | 摘要 |
| `contractor` | 承建商（選填） |
| `contractorConfidence` | 承建商資料可信度說明（選填） |
| `sources` | `[{ "outlet", "url" }, …]` |
| `image` | 圖片相對路徑（選填，例如 `assets/news/example.jpg`） |

頁面介紹香港註冊安全主任及註冊安全審核員提供的安全及環保顧問、風險評估、安全審核、消防及起重機械檢驗、ISO 驗證等服務，並提供聯絡方式。

## 本地預覽

在專案根目錄啟動簡易靜態伺服器即可，例如：

```bash
python3 -m http.server 8080
```

於瀏覽器開啟 `http://localhost:8080/`。

## GitHub Pages

建議使用 **Settings → Pages → Build and deployment → Deploy from a branch**，來源分支 **`main`**、資料夾 **`/ (root)`**。

公開網址（啟用後）：

https://tonysafety.github.io/synergy-safety/

新聞頁：`https://tonysafety.github.io/synergy-safety/news.html`

若儲存庫為 **Private**，需先改為 **Public**（或使用支援私人 Pages 的 GitHub 方案），並在 Pages 設定中啟用網站；此 Cloud Agent 的整合權限無法代為開啟 Pages API。
