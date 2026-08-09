# Atlas Investment Terminal 2.0

一个本地运行的 A 股投资研究终端，用于市场监控、股票池管理、公司研究、估值分析、组合风险和 AI 辅助研究。

Atlas 只提供研究与决策支持；不连接券商，不执行自动交易。

## 项目入口

- `app/`：Streamlit 仪表盘与页面组件。
- `backend/`：FastAPI 接口、业务服务和数据库访问。
- `data/`：行情、财务数据及本地缓存。
- `quant/`：因子、回测和选股模型。
- `ai/`：研究分析与投资委员会。
- `portfolio/`：持仓、风险、Thesis、决策日志和压力测试。
- `config/`：非敏感配置模板。
- `tests/`：自动化测试。
- `docs/`：架构、迁移和使用说明。
- `legacy/openclaw-atlas/`：旧 OpenClaw Atlas 的完整归档，仅供提取投资思想资产与历史参考。

## 目录约定

- 代码与模块目录使用英文，保持 Python、Streamlit 和 FastAPI 生态的通用性。
- 研究笔记、投资规则和面向使用者的文档可使用中文。
- 新功能只能进入对应的新模块；不要向 `legacy/` 添加业务代码或日常产出。
- 所有行情、财务或 AI 输出均需保留数据来源与生成时间。
- 自动交易、券商下单和未经确认的账户操作均不在本项目范围内。

## 当前阶段

已完成旧 Atlas 资产归档和新项目根目录规范化。下一步是依据迁移报告建立最小可运行的数据层与仪表盘基础，而不是直接复用旧脚本。

## 初始化本地数据

首次建立本地 SQLite 数据库并导入已归档的历史资产：

```bash
python3 -m backend.services.initialize_atlas
```

该命令只创建 `data/atlas.db`，导入旧持仓、投资者画像、决策日志和唯一生效的风险预算；不会连接券商、获取实时行情或执行交易。

## 启动终端

先启动本地 API：

```bash
.venv/bin/uvicorn backend.api.app:app --reload
```

另开一个终端启动 Streamlit：

```bash
.venv/bin/streamlit run app/dashboard/main.py
```

默认 API 地址为 `http://127.0.0.1:8000`；如需覆盖，设置 `ATLAS_API_URL`。市场概览优先尝试 AkShare，失败时回退腾讯行情；任何来源不可用都会在页面中明确标注。

## 单股财务刷新与只读缓存

`POST /api/v1/stocks/{symbol}/financials/refresh` 使用 AkShare 同花顺关键指标刷新单只股票的财务数据，并把报告期指标标准化后写入 SQLite 的 `financial_metrics` 缓存表。金额统一换算为人民币元，比率统一保存为百分比、倍数或天数，避免把“万/亿/%”等展示格式混入数据层。

`GET /api/v1/stocks/{symbol}` 返回 `financials` 只读缓存，包含最新报告期、指标来源、刷新时间和最近报告期历史；估值 PE/PB/市值从历史快照回退展示。选股器优先使用该规范化缓存，ROE 与营收同比已纳入筛选，legacy 仅作为缺失指标的历史回退。股票详情页只展示缓存，不提供手动编辑；页面上的“刷新财务数据”按钮会调用上述 API。

批量刷新全部、自选或持仓股票：

```bash
.venv/bin/python -m backend.services.refresh_financials --scope all
.venv/bin/python -m backend.services.refresh_financials --scope watchlist
.venv/bin/python -m backend.services.refresh_financials --symbols 000021.SZ,601899.SH
```

也可以调用 `POST /api/v1/stocks/financials/refresh?symbols=000021.SZ,601899.SH`。详情页会显示财务缓存与估值快照距今的时间，避免把陈旧数据误读为实时数据。

## 股票主数据

新增或更新一只 A 股主数据：

```bash
.venv/bin/python -m backend.services.stock_master --symbol 600000.SH --name 浦发银行
```

也可以调用 `POST /api/v1/stocks`，请求体例如 `{"symbol": "600000.SH", "name": "浦发银行"}`。服务会优先尝试用 AkShare 补全交易所和行业；补全失败时使用用户提供的名称创建记录，不会把缺失字段估算成事实。新股票创建后即可用单股财务刷新接口拉取缓存。

## 行情持久化缓存

每次成功的行情请求会写入 SQLite 的 `market_quote_cache` 表。当网络或上游数据源不可用时，市场概览、自选股和股票详情会回退到最近一次成功快照，并在页面标记为“历史缓存”，避免把旧行情伪装成实时数据。内存 TTL 缓存继续用于减少交互刷新次数。

## 市场广度

`/api/v1/market/overview` 使用 AkShare 的 `stock_zh_a_spot_em` 全市场快照计算上涨/下跌/平盘家数、涨停/跌停家数和全市场成交额，Eastmoney 不可用时回退到新浪 `stock_zh_a_spot`。涨停/跌停按主板、创业板/科创板、北交所和 ST 的涨跌幅限制分别判断；所有上游不可用时返回 `status: "unavailable"` 并附原因，不估算缺失值。

成功的广度快照会写入 SQLite 的 `market_breadth_cache` 表，默认 15 分钟 TTL。缓存命中时直接返回，上游失败时回退最近一次成功快照，并在页面标记为“历史缓存”。

## 每日流水线

统一入口一次完成：拉取并持久化行情、计算市场广度、刷新财务缓存（可选）、保存本地晨报快照、生成 Markdown 报告和机器可读运行清单。

```bash
.venv/bin/python -m backend.services.daily_run --financial-scope watchlist
```

报告写入 `reports/daily/YYYY-MM-DD/`，终端输出 JSON manifest，包含市场可用状态、广度状态、财务刷新摘要、晨报快照 ID 和报告路径。`--financial-scope` 支持 `none`、`watchlist`、`portfolio`、`all`。

## 定时任务

macOS LaunchAgent 会在工作日 08:30 自动运行每日流水线并刷新自选股财务缓存：

```bash
scripts/install_daily_launchagent.sh
```

日志写入 `data/logs/daily_run.out.log` 和 `data/logs/daily_run.err.log`。如需停止：

```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.daily.plist
```

## 依赖与 CI

- `requirements.txt` 锁定顶层运行依赖版本。
- `requirements.lock.txt` 锁定完整虚拟环境版本，供 CI 复现。
- 本地 `.venv` 使用 Python 3.12，锁定依赖已在 Python 3.12 下完整安装并通过全量测试。
- `.github/workflows/ci.yml` 在推送和 Pull Request 时安装锁定依赖并运行全量测试。

## 迁移资料

- 旧系统架构审计：`docs/reference/legacy-architecture-audit-2026-08-08.md`
- 旧系统归档：`legacy/openclaw-atlas/`
