# Atlas 2.0 Foundation Design

## Goal

建立 Atlas 2.0 的本地 SQLite 基础：保留旧 Atlas 的投资资产，提供唯一、版本化的风险规则来源，并让后续 Dashboard/API 只通过新数据库读取数据。

## Scope

本阶段包含：SQLite schema、数据库初始化、风险预算版本、旧持仓/投资者画像/决策日志的只读导入，以及可重复运行的验证测试。

本阶段不包含：行情抓取、自动交易、券商连接、FastAPI 路由、Streamlit 页面、AI 调用或实时估值。

## Architecture

`backend/database/` 负责连接、建表和事务；`backend/services/` 负责风险预算与旧资产导入；`portfolio/` 保留领域概念。运行库仅使用 Python 标准库 SQLite，数据库文件位于 `data/atlas.db`，不进入 Git。

旧文件只读：`legacy/openclaw-atlas/` 是迁移输入与历史审计证据，不会被新代码修改。每条导入记录会写入 `source_path`、`source_as_of` 和 `imported_at`。

## Canonical Risk Rule

Atlas 2.0 首个生效规则版本采用旧 `portfolio/仓位预算.md` 的 A 股三层仓位预算：核心仓单股 15%、行业 40%；成长仓单股 8%、行业 30%；主题仓单股 3%、主题总计 10%；现金最低 20%；禁止杠杆；组合单日损失 -3% 触发 review。

旧 `core/risk_rules.py` 的 LOW/MEDIUM/HIGH 10%/5%/2% 规则作为“历史规则”保存，不参与合规判断。新版本不得同时应用两套限制。

## Data Model

- `investor_profiles`：投资者类型、周期、风险偏好和来源。
- `risk_budget_versions`：风险规则版本、状态、JSON 规则体、来源和生效时间。
- `stocks`：标准股票代码、名称、交易所、行业分类。
- `portfolio_snapshots` 与 `portfolio_positions`：指定日期持仓快照及仓位明细。
- `decisions`：导入的决策事件、论点、验证指标和失效条件原文。
- `import_runs`：导入运行状态与来源文件，保证重跑可追溯。

## Error Handling

导入失败时整体回滚，不产生部分持仓。缺失、未知或无法严格解析的字段保留为空并记录到 `import_runs.details`；不得以估算值补齐。重复执行同一来源与同一日期时不重复写入。

## Testing

使用 Python 标准库 `unittest`。测试覆盖建表幂等、唯一生效风险规则、JSON 持仓导入、决策日志识别、来源记录与重复导入不重复写入。

## Constraints

- 不执行交易或生成买卖指令。
- 不把历史价格、回退数据或迁移数据标示为实时数据。
- 所有金融数据必须保留来源和时间。
- 每次代码修改前在工作说明中列出文件、原因与影响范围。
