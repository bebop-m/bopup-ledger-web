# 波普账本 Bopup Ledger

一个面向移动端的纯静态股息账本。前端负责持仓管理、收益计算和展示；行情、股息和汇率通过 GitHub Actions 生成 `data/market.json`；页面本身托管在 GitHub Pages。

## 当前架构

```text
公开仓库（bebop-ledger-web）
  - 网页代码：index.html / styles.css / app.js
  - 公共数据：data/market.json / data/watchlist.json / data/override.json
  - GitHub Pages 静态部署

私有仓库（bebop-ledger-private）
  - 个人真实持仓快照：data/portfolio.json

浏览器本地（localStorage）
  - 当前设备上的运行态持仓
  - UI 状态
  - GitHub Personal Access Token
```

## 数据流

```text
Update Market Data
  -> Python 脚本抓取价格、股息、汇率
  -> 写入公开仓库 data/market.json

Deploy Pages
  -> 将公开仓库代码和 data 目录打包部署到 GitHub Pages
  -> 在 Update Market Data 成功后自动重新部署

前端页面
  -> 优先读取站点上的 data/market.json
  -> 合并 data/override.json 的手动股息覆盖
  -> 再用腾讯实时价格覆盖 price / previousClose
  -> 所有持仓计算都在前端完成
```

## 当前功能

### 持仓与收益

- 展示总市值、总股息、汇率、负债和净资产
- 支持核心仓 / 打工仓分组
- 支持按市值、股息率、股息金额排序
- 展示每只股票的价格、市值、数量、税后股息、股息率和占比
- 支持数量、税率、每股 TTM 股息手动覆盖

### 同步

- 当前 UI 默认只暴露一个“云同步”入口
- 第一次在新设备点击云同步时，需要输入一次 GitHub Personal Access Token
- Token 保存在浏览器 `localStorage`
- 如果本地还是模板态，云同步会先尝试从私有仓库恢复真实持仓
- 如果本地已经是真实持仓，云同步会上传到私有仓库 `data/portfolio.json`
- 如果真实持仓里出现了新的股票代码，云同步会自动把它追加进公开仓库 `data/watchlist.json`
- 追加成功后会自动触发 `Update Market Data`
- 云按钮会在后台持续工作并显示旋转动画；页面本身不锁死，可以继续使用

### 行情与股息

- 价格：腾讯实时行情优先用于前端覆盖
- 股息：由后台脚本写入 `dividendPerShareTtm`
- 股息来源状态：`yfinance` / `cache` / `manual`
- Tooltip 会显示股息来源、更新时间、最近除息日，以及抓取错误（如果有）

## 公开数据与私有数据的边界

### 公开仓库中的数据

- `data/market.json`
- `data/watchlist.json`
- `data/override.json`

这些文件会进入 GitHub Pages，任何访问站点的人都可以读取。

### 私有仓库中的数据

- `data/portfolio.json`

这个文件只放在私有仓库，不在公开仓库中，也不会部署到 GitHub Pages。

## 文件说明

### 公开仓库

```text
index.html
styles.css
app.js
config.json
assets/
data/
  market.json
  override.json
  watchlist.json
scripts/
  update_market_data.py
  requirements.txt
.github/workflows/
  update-market-data.yml
  deploy-pages.yml
serve.ps1
```

### 关键文件

- `data/market.json`
  后台自动生成的公共行情快照，包含价格、每股 TTM 股息、股息来源、更新时间、最近除息日、状态和汇率。

- `data/watchlist.json`
  公共观察名单，也是后台更新股票池。前端新增真实持仓后，云同步会自动把缺失的 symbol 追加进来。

- `data/override.json`
  手动股息覆盖，优先级高于后台抓取结果。

- `config.json`
  轻量配置文件，目前主要控制 `coreSymbols` 和 `staleDays`。

- `scripts/update_market_data.py`
  后台行情脚本。负责抓取价格、股息、汇率并写入 `data/market.json`。

### 私有仓库

```text
data/
  portfolio.json
```

- `data/portfolio.json`
  个人真实持仓快照，用于跨设备恢复和备份。

## 股息计算

前端只认 `dividendPerShareTtm` 这个核心字段：

```text
股息率 = dividendPerShareTtm / 当前价格
税前年度股息 = dividendPerShareTtm * 持股数量 * 汇率
税后年度股息 = 税前年度股息 * (1 - 税率)
```

手动覆盖优先级高于后台值。

## 本地预览

```powershell
powershell -ExecutionPolicy Bypass -File serve.ps1
```

打开：

```text
http://127.0.0.1:4173/
```

## 部署

本项目当前使用 GitHub Actions + GitHub Pages。

### 需要的工作流

- `update-market-data.yml`
  负责更新公开仓库里的 `data/market.json`

- `deploy-pages.yml`
  负责部署页面，并会在 `Update Market Data` 成功后自动再次部署，确保站点里的 `data/market.json` 跟上最新版本

### 推荐的同步 Token 权限

使用 fine-grained personal access token，并只授权这两个仓库：

- `bebop-ledger-web`
- `bebop-ledger-private`

最小权限：

- `Contents: Read and write`
- `Actions: Read and write`

## 当前已知事实

- 页面默认模板和真实持仓是两套概念
- `watchlist.json` 是公共观察池，不是私有持仓快照
- 私有真实持仓不再放在公开仓库里
- `Update Market Data` 更新后，Pages 也会自动重新部署
