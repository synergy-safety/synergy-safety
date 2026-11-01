# 協同安全顧問公司｜Synergy Safety Consultant Company

此儲存庫為 **協同安全顧問公司** 的官方靜態落地頁，部署於 GitHub Pages。

## 內容

- 語言：**繁體中文**（`zh-Hant-HK`），並附英文公司名稱與服務標題
- 根目錄：`index.html`、`styles.css`
- 品牌標誌：`assets/logo.png`

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

若儲存庫為 **Private**，需先改為 **Public**（或使用支援私人 Pages 的 GitHub 方案），並在 Pages 設定中啟用網站；此 Cloud Agent 的整合權限無法代為開啟 Pages API。
