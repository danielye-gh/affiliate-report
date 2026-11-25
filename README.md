# Affiliate Report

从 **Impact、Awin** 等联盟平台及 **Shopify** 拉取月度 Actions（转化/交易）报表，与 Shopify 订单归因对账，并导出审单用 Excel 工作簿。

> **CJ 已停用**：月报流水线与 CLI 中的 CJ 拉取/对账已注释；`platforms/cj`、`reconcile/cj` 等代码仍保留，恢复时按源码中 `CJ disabled` 注释取消即可。

## 项目结构

```
src/affiliate_report/
├── base/                 # 各平台共享抽象接口
├── platforms/
│   ├── impact/           # Impact API（ReportExport + Actions）
│   ├── cj/               # CJ Commission Detail GraphQL API（已停用，代码保留）
│   ├── awin/             # Awin Advertiser Transaction API（DE / UK）
│   └── shopify/          # Shopify Sales Attribution + UTM 联盟订单
├── preprocess/           # 各平台原始数据 → 标准 parquet
├── reconcile/            # 联盟数据 × Shopify 对账 enriched CSV
├── pipeline/             # 月度全流程 + Excel 汇总
├── impact_filters.py     # Impact 报表筛选（Channel / Status / Currency）
└── cli.py                # 命令行入口
```

每个联盟平台独立目录，接口逻辑不混写在同一文件里。

## Windows 用户

Windows 10/11 可直接使用项目根目录的批处理脚本，无需手动配置 PATH：

1. 双击 **`setup.bat`** 创建虚拟环境并安装依赖（自动识别 `py` 或 `python`）
2. 编辑 **`.env`** 填入 API 凭证
3. 双击 **`report.bat`** 打开图形界面，或命令行：`report.bat 2026 5`

详细说明见 **[Windows使用说明.md](Windows使用说明.md)**。

## macOS / Linux 用户

```bash
chmod +x setup.sh report.sh
./setup.sh
# 编辑 .env 填入凭证后：
./report.sh              # GUI
./report.sh 2026 5       # 命令行
./report.sh 2026 5 skip  # 跳过 API 拉取
```

Windows 的 `setup.bat` / `report.bat` 保持可用，互不影响。

## 在线更新

GUI 中点击 **在线更新**，或命令行：

```bash
report.bat update    # Windows
./report.sh update   # macOS / Linux
```

从 GitHub 下载最新代码覆盖本地程序文件，**不会改动** `.env`、`data/`、`.venv/`。
更新源按优先级取：`.env` 中的 `UPDATE_REPO` → `updater.py` 中的 `DEFAULT_REPO` → 本地 git remote。
发布到 GitHub 后请在 `src/affiliate_report/updater.py` 里把 `DEFAULT_REPO` 填成实际仓库（如 `your-name/affiliate-report`），这样分发给用户的副本才能直接更新。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .

cp .env.example .env        # 若尚无 .env
# 填入各平台凭证（见下文配置说明）
```

## 推荐：一条命令生成月度审单表

`report` 会依次：**拉取各平台 + Shopify 全量报告 → 对账处理 → 导出 Excel**。

```bash
# 完整流程（需网络与各平台 API 凭证）
affiliate-report report --year 2026 --month 5

# 已有 data/raw/ 数据时跳过拉取，只做对账与导出
affiliate-report report --year 2026 --month 5 --skip-fetch

# 指定输出路径
affiliate-report report --year 2026 --month 5 --output data/reports/my_report.xlsx
```

默认输出：`data/reports/affiliate_report_2026-05.xlsx`

Impact 导出由服务器排队处理，默认最多等待 30 分钟。可在 `.env` 设置
`IMPACT_EXPORT_MAX_WAIT_SECONDS=3600` 调整到 60 分钟。等待超时不代表服务器任务失败，
程序不会自动重建或重放任务。可使用日志中的任务 ID 继续等待并下载原任务：

```bash
affiliate-report impact poll-job --job-id <任务ID> --output data/raw/impact/actions_2026-11.csv
```

该命令只恢复指定 Impact 导出文件，不自动重跑整份月报。

### 数据库补充归因

Impact、Awin-DE、Awin-UK 对账会查询 DTC 表
`dwd_wb_shopify_orders_original_sku_detail_di`，在原归因列旁新增「补充归因」。
请在本地 `.env` 填写 `DTC_DATABASE_USER`、`DTC_DATABASE_PASSWORD`；连接地址等可选配置见 `.env.example`。
凭据不写入代码或报表，连接使用 TLS 并校验证书。

- Impact 使用订单名称去掉 `#` 对齐 OID；Awin 使用数字订单 ID 对齐 extra，均限定店铺。
- 只采用数据库 `last_visit_utm_source` 中的 `impact` / `awin`（忽略大小写和首尾空格）。
- 补充归因有值时优先用于匹配判断，否则沿用 Shopify 原归因；原归因列保留供对照。
- Shopify 来源字段统一为 `order_utm_source`，只取 `customerJourneySummary.lastVisit.utmParameters.source`（末次访问）；末次为空时保持为空，不回退首次访问。该字段用于原归因展示、联盟筛选及订单匹配；补充归因优先级不变。
- 旧版 `orderUtmSource` 缓存可能含首次访问回退，无法直接改名恢复正确口径。更新后须重新拉取 Shopify 全量及联盟数据：`affiliate-report fetch shopify --year 2026 --month 11 --report all`（按实际月份调整），之后才可使用 `--skip-fetch`。
- Shopify 全量明细及 `impact-shopify`、`awin-shopify` 表也展示「补充归因」。联盟 Shopify 表取并集：原 Shopify 归因或补充归因为该联盟即保留，包括原归因为其他渠道、数据库补充为联盟的订单；原归因与补充归因跨联盟时，两张表均保留以供比较。相同订单事件不因两种来源同时命中而重复加入，原有订单/退款行保持完整。
- 生成 Excel 时从全量 `sales_attribution` 重建以上并集，`--skip-fetch` 也适用，不依赖旧的联盟筛选文件；审单匹配仍以补充归因优先。
- 匹配结果继续进入既有 Action 规则和 Summary；退款、佣金、专属码规则的优先级不变。
- 按报表订单批量查询，不限制销售发生日期。同一订单先取最新刷新时间，再按销售时间、销售日期排序，然后判断最新来源是否为 impact/awin；最新来源为其他渠道或空值时不使用历史联盟归因。同一时点来源冲突时报错。
- Shopify 未找到但数据库找到的订单也能补充归因，退款信息仍为空，不推断为「无退款」。
- 数据库失败或缺少凭据会终止处理。`--skip-fetch` 只跳过平台 API 拉取，仍会查询数据库。

归因回归检查：`PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`。

### Excel 工作表（14 个 sheet）

| Sheet | 内容 |
|-------|------|
| `Impact-Summary` | Impact 按 Partner 匹配汇总 |
| ~~`CJ-Summary`~~ | （CJ 已停用） |
| `Awin-DE-Summary` | Awin DE 按 publisher 匹配汇总 |
| `Awin-UK-Summary` | Awin UK 按 publisher 匹配汇总 |
| `Impact` | Impact 对账表 |
| ~~`CJ`~~ | （CJ 已停用） |
| `Awin-DE` | Awin 德国 |
| `Awin-UK` | Awin 英国 |
| `sales_attribution-us` | Shopify US 全量订单 |
| `sales_attribution-de` | Shopify DE 全量订单 |
| `sales_attribution-uk` | Shopify UK 全量订单 |
| ~~`cj-shopify`~~ | （CJ 已停用；`--report all` 不再拉取） |
| `impact-shopify` | Impact 联盟订单（US+DE+UK） |
| `awin-shopify` | Awin 联盟订单（US+DE+UK） |

中间对账 CSV 同时写入 `data/processed/{impact,cj,awin}/`。

---

## 对账处理（`process`）

在已有原始数据与 Shopify `sales_attribution` 的前提下，单独跑某一平台对账：

```bash
affiliate-report process impact --year 2026 --month 5
# affiliate-report process cj --year 2026 --month 5  # CJ 已停用
affiliate-report process awin --year 2026 --month 5
affiliate-report process awin --year 2026 --month 5 --site de
```

### 输出文件

| 平台 | 路径 |
|------|------|
| Impact | `data/processed/impact/impact_actions_2026-05_enriched.csv` |
| ~~CJ~~ | （已停用） |
| Awin | `data/processed/awin/awin_actions_2026-05_{de,uk}_enriched.csv` |

### Shopify 匹配规则

| 平台 | 匹配键 | Shopify 数据源 |
|------|--------|----------------|
| Impact | `OID`（订单号） | **US + UK + DE + FR + AU**（`2022`/`2220` 前缀→UK，`2023`/`2320` 前缀→DE，`2420` 前缀→FR，`2620` 前缀→AU，其余→US） |
| ~~CJ~~ | （已停用） | — |
| Awin | `extra` / `orderRef` | 与 Awin 站点对应：**DE→DE，UK→UK** |

匹配成功条件：在对应 Shopify 报告中找到订单，且 `utm_source` 为 `impact` / `awin`（CJ 已停用）。

### Action 列规则

按优先级依次处理（后一步不会覆盖更高优先级已定的结果）：

| 优先级 | 条件 | Action |
|--------|------|--------|
| 1 | 佣金为 0（Impact `Action Cost`、Awin `commission`） | `通过` |
| 2 | 佣金 ≠ 0 且 `shopify是否退款` 为 `1`（全额）或 `2`（部分） | `取消` |
| 3a | 佣金 ≠ 0、未退款，且 Shopify 匹配成功 | `通过` |
| 3b | 佣金 ≠ 0、未退款，且使用了该媒体独家折扣码（`exclusive_codes.csv`） | `通过` |
| 3c | 该媒体订单量 `Total ≤ 2`：尚未判定的订单全部 `通过` | `通过` |
| 3d | 该媒体订单量 `2 < Total ≤ 5`：保证通过率 ≥ 50%（`ceil(Total/2)`）；在已有 `通过` 基础上补足，优先通过佣金最低且尚未判定的订单 | `通过` |
| 3e | 其余尚未判定的订单 | `取消` |

说明：
- `shopify是否退款`：在 Shopify 全量订单中**找到该订单**时必填——`0` = 未退款，`1` = 全额退款，`2` = 部分退款（与 utm 是否匹配无关）。**仅当 Shopify 中找不到该订单时为空**。Action 对 `1`/`2` 同等按「有退款」处理。
- `shopify退款金额`：找到订单且有退款时填写退款合计；未退款或找不到订单为空。
- 全额/部分判定：订单当前 `netSales`（Shopify `currentSubtotalPriceSet`，已扣退款）≤ 0 为全额，否则为部分。
- 「匹配情况」= Shopify 中有该订单 **且** `utm_source` 为当前平台（impact/awin）；退款字段只依赖「订单是否存在」，不依赖匹配。
- 独家 code 以 **Shopify 订单折扣码**（`discountCode`）为准；仅对 CSV 中列出的媒体补 `通过`，不再单独整媒体覆盖。
- 订单量规则不会覆盖优先级 1/2 已定的结果（如有退款的非零佣金仍为 `取消`）。
- Total > 5 时不做 3c/3d 补通过；未匹配且无独家 code 的订单最终为 `取消`（零佣金 / ≤2 单媒体除外）。

本地 CSV 可离线编辑；配置了飞书应用后可用：

```bash
affiliate-report exclusive-codes sync
affiliate-report exclusive-codes path
```

未匹配但 Shopify 有订单时，Impact 仍会填 `attribution`（`utm_source`）。

---

## 拉取原始数据（`fetch`）

### Impact

与 Impact 后台 **Advanced Action Listing** 一致，请用 **`--method report`**（默认）：

```bash
affiliate-report impact list-reports

affiliate-report fetch impact --year 2026 --month 5 --method report
affiliate-report fetch impact --year 2026 --month 5 -v
```

输出：`data/raw/impact/actions_2026-05.csv`

| 方式 | 命令 | 说明 |
|------|------|------|
| **report**（推荐） | `--method report` | ReportExport，与 UI 报表一致 |
| report-sync | `--method report-sync` | 同步接口（需 Reports Run 权限） |
| actions | `--method actions` | 原始 Actions API，**不含 UI 筛选** |

要对账请始终用 `--method report`。

手动轮询 ReportExport Job：

```bash
affiliate-report impact poll-job \
  --queued-uri "/Advertisers/<AccountSID>/Jobs/<job-id>.json"
```

### Awin

```bash
affiliate-report awin list-accounts

affiliate-report fetch awin --year 2026 --month 5
affiliate-report fetch awin --year 2026 --month 5 --site de
affiliate-report fetch awin --year 2026 --month 5 --site uk
```

输出：`data/raw/awin/{de,uk}/actions_2026-05.json`、`publishers.json`（Partner 目录，用于对账表 `publisher` 列）

接口：
- `GET /advertisers/{advertiserId}/transactions/`
- `GET /advertisers/{advertiserId}/publishers`（Partner 公司名目录）

| 变量 | 说明 |
|------|------|
| `AWIN_API_TOKEN` | API OAuth token |
| `AWIN_ADVERTISER_ID_DE` | DE Advertiser ID（在 Awin 后台或 `awin list-accounts` 查看） |
| `AWIN_ADVERTISER_ID_UK` | UK Advertiser ID（同上） |

### CJ（已停用）

代码与配置项仍保留；月报 / `fetch cj` / `process cj` / `cj probe` 已从 CLI 与流水线注释。恢复时搜索源码中的 `CJ disabled`。

### Shopify

拉取订单 + UTM 归因，对齐审单表字段。

| 报告 | 说明 | UTM 过滤 |
|------|------|----------|
| `sales-attribution` | 全部订单 | 无 |
| ~~`cj-shopify`~~ | （CJ 已停用；可用 `--report cj-shopify` 手动拉） | `utm_source=cj` |
| `impact-shopify` | Impact 联盟订单 | `utm_source=impact` |
| `awin-shopify` | Awin 联盟订单 | `utm_source=awin` |

```bash
# 全部站点 × 默认报告（不含 cj-shopify）
affiliate-report fetch shopify --year 2026 --month 5

# 单站点 / 单报告
affiliate-report fetch shopify --year 2026 --month 5 --site us
affiliate-report fetch shopify --year 2026 --month 5 --site us --report impact-shopify
```

输出示例（US）：

```
data/raw/shopify/us/sales_attribution/sales_attribution_2026-05.json
data/raw/shopify/us/impact_shopify/impact_shopify_2026-05.json
data/raw/shopify/us/awin_shopify/awin_shopify_2026-05.json
```

**时区**：`minute` 按店铺 IANA 时区格式化（如 US 店 `Asia/Hong_Kong`），与后台下载报告一致；可选手动设置 `SHOPIFY_TIMEZONE_US` 等。

**查询窗口**：月度拉取在目标月前后各多取 **1 天**，覆盖各平台时区边界订单。

| 变量 | 说明 |
|------|------|
| `SHOPIFY_SHOP_US` / `SHOPIFY_ACCESS_TOKEN_US` | US 店铺 |
| `SHOPIFY_SHOP_DE` / `SHOPIFY_ACCESS_TOKEN_DE` | DE 店铺 |
| `SHOPIFY_SHOP_UK` / `SHOPIFY_ACCESS_TOKEN_UK` | UK 店铺 |
| `SHOPIFY_SHOP_FR` / `SHOPIFY_ACCESS_TOKEN_FR` | FR 店铺 |
| `SHOPIFY_SHOP_AU` / `SHOPIFY_ACCESS_TOKEN_AU` | AU 店铺 |
| ~~`SHOPIFY_CJ_UTM_SOURCE`~~ | （CJ 已停用） |
| `SHOPIFY_IMPACT_UTM_SOURCE` | 默认 `impact` |
| `SHOPIFY_AWIN_UTM_SOURCE` | 默认 `awin` |

---

## Impact 配置说明

| 变量 | 说明 |
|------|------|
| `IMPACT_ACCOUNT_SID` | Account SID |
| `IMPACT_AUTH_TOKEN` | Auth Token |
| `IMPACT_ACCOUNT_TYPE` | `advertiser` 或 `mediapartner` |
| `IMPACT_PROGRAM_ID` | Campaign / Program ID（advertiser 必填，在 Impact 后台查看） |
| `IMPACT_ACTION_REPORT_HANDLE` | 默认 `adv_action_listing_pm_only` |

报表筛选（仅 `report` / `report-sync`）：

| 变量 | 说明 |
|------|------|
| `IMPACT_REPORT_CHANNEL` | 如 `Affiliate/CPA Network` |
| `IMPACT_REPORT_CURRENCY` | 如 `USD` |
| `IMPACT_REPORT_ACTION_STATUS` | 逗号分隔，如 `Approved,Pending,Reversed`；ReportExport 会传 `ACTION_STATUS`，若报表本身缺状态（如 `*_pm_only` 只有 Pending）则自动用 Actions API 补拉 |

---

## 数据目录

```
data/
├── config/
│   ├── exclusive_codes.example.csv  # 格式示例（可公开）
│   └── exclusive_codes.csv          # 本地真实配置（不入库，首次运行从 example 复制）
├── raw/                  # 各平台 API 原始导出
│   ├── impact/
│   ├── cj/
│   ├── awin/{de,uk}/
│   └── shopify/{us,de,uk}/...
├── processed/            # 对账 enriched CSV
│   ├── impact/
│   ├── cj/
│   └── awin/
└── reports/              # 月度 Excel 工作簿
    └── affiliate_report_YYYY-MM.xlsx
```

## 数值格式

对账 CSV / Excel 中：**金额与比率**保留 2 位小数，`0` 显示为 `0.00`；真正缺失的字段留空。

---

## 命令速查

```bash
# 月度审单（推荐）
affiliate-report report --year 2026 --month 5

# 单平台拉取
affiliate-report fetch impact --year 2026 --month 5
# affiliate-report fetch cj --year 2026 --month 5  # CJ 已停用
affiliate-report fetch awin --year 2026 --month 5
affiliate-report fetch shopify --year 2026 --month 5

# 单平台对账
affiliate-report process impact --year 2026 --month 5
# affiliate-report process cj --year 2026 --month 5  # CJ 已停用
affiliate-report process awin --year 2026 --month 5

# 独家 Code 配置
affiliate-report exclusive-codes path
affiliate-report exclusive-codes sync
```
