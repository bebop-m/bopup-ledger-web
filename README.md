# 波普账本网页端

这版网页已经收成纯静态方案：

- 前端页面只读取 `data/market.json`
- `GitHub Actions` 每 5 分钟自动更新一次价格和汇率
- `Netlify` 或 `GitHub Pages` 只负责托管静态文件
- 不再依赖 Longbridge、Netlify Functions 或本地常驻服务

## 当前能力

- 资产总览
- 公司占比圆环图
- 核心仓 / 打工仓横向占比条
- 本地持仓保存
- 新增、删除
- 数量弹窗编辑
- 税率弹窗编辑
- 按持仓市值 / 股息率排序
- 隐私隐藏
- AKShare 定时刷新价格
- Frankfurter 定时刷新汇率
- 港股 TTM 股息率自动更新
- A 股 TTM 股息率自动计算

## 关键文件

- `data/watchlist.json`
- `data/market.json`
- `scripts/update_market_data.py`
- `scripts/requirements.txt`
- `.github/workflows/update-market-data.yml`

## 架构

```text
GitHub Actions
  -> 运行 Python 脚本
  -> 从 AKShare 拉股票价格
  -> 从 Frankfurter 拉汇率
  -> 港股直接读取 TTM 股息指标
  -> A 股按最近 12 个月分红自行计算 TTM 股息率
  -> 更新 data/market.json
  -> 提交回仓库

静态网页
  -> 刷新时读取 data/market.json
```

## 本地预览

```powershell
powershell -ExecutionPolicy Bypass -File "C:\GPT CODEX\web-app\serve.ps1"
```

打开：

```text
http://127.0.0.1:4173/
```

## GitHub 自动更新

工作流会：

- 每 5 分钟运行一次
- 更新 `data/market.json`
- 自动提交最新行情文件

如果你是用 GitHub 网页手动上传文件，记得把隐藏目录 `.github` 也一起上传，否则工作流不会生效。

## 重要限制

### 观察名单限制

自动更新只覆盖 `data/watchlist.json` 里的股票。

也就是说：

- 你在网页里新增了一只新股票
- 想让它也自动刷新价格
- 还需要把它补进 `data/watchlist.json`

### 港股时效

AKShare 文档注明港股行情通常是 15 分钟延时。

### 股息率

- 港股：直接使用 AKShare 的 TTM 字段
- A 股：根据最近 12 个月现金分红自行计算
- 美股：当前不做自动股息率