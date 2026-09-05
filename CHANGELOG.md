# Changelog

本项目所有值得关注的变更都记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 修复

- **修复 CI 测试收集失败**：`scripts/test_news_sources.py` 中的 `test_sources(fetcher)`
  是 CLI 诊断函数，但文件名与函数名同时命中 pytest 的默认收集规则，
  CI 执行不带路径参数的 `pytest` 时会把它当测试用例收集，
  因 `fetcher` 参数无对应 fixture 而报 collection error
  （本地跑 `pytest tests/` 无法复现）。三重修复：
  - 脚本重命名为 `scripts/check_news_sources.py`，函数改名 `check_sources`；
  - 新增 `pytest.ini` 固定 `testpaths = tests`，裸 `pytest` 也只收集测试目录；
  - CI 的测试步骤显式改为 `pytest tests`。
- **忽略 `.pytest_tmp/`**：本地绕过沙箱 `tmp_path` 权限限制所用的 `--basetemp`
  产物目录已加入 `.gitignore`，避免误入库。

- **消除重复方法定义**：`TechnicalAnalyzer`、`NewsFetcher`、`LLMAnalyzer`、
  `DingTalkNotifier` 中存在同名方法被定义两次的问题，后定义者静默覆盖前者，
  导致实际运行的是缺乏异常保护的低质量实现。具体影响：
  - `calculate_rsi` 生效版本使用 `gain / loss`，在无下跌的单边行情中会
    **除零产生 inf**；已改用带平滑项的实现并补充边界校验。
  - `calculate_bollinger` 生效版本缺少 `min_periods`，前 20 根产生大段 NaN。
  - `get_trend_analysis` 生效版本不返回 `ma_alignment` / `bb_position`，
    导致报告与 LLM 提示词中对应区块长期缺失。
  - `DingTalkNotifier` 的 `_send_request` 生效版本吞掉异常仅返回 False，
    上层无法感知具体错误。
- **修复 LLM 分析结果解析失配**：提示词要求模型返回结构化文本，
  而生效的解析器只处理 JSON，导致 `analysis` 字段长期为 `None`。
  现改为 JSON 优先、正则抽取兜底的双通道解析。
- **清理不可达死代码**：`technical.py` 中 `_cluster_levels` 的 `return` 之后
  残留 MACD 计算片段；`dingtalk.py` 中 `raise` 之后残留 payload 构造逻辑。
- **修复新闻源类型支持不全**：`fetch_news_from_source` 此前仅支持 `rss`，
  配置中的 `html` / `api` 类型源会被跳过；现已补全。
- **修复支撑阻力位方向颠倒**：所有摆动低点被无条件归为支撑、高点归为阻力，
  未按当前价过滤，导致报告出现「第一支撑 $4500.94 高于现价 $4436.42」
  这类自相矛盾的点位，直接损害投研可信度。现按角色互换原理重新归类：
  支撑必须位于现价下方、阻力必须位于现价上方，且按贴近现价排序。
- **修复未配置项被误判为已配置**：`ConfigLoader` 在环境变量缺失时原样保留
  `${VAR}` 字面量，下游 `if webhook_url:` 判定为真，于是用 `'${SLACK_WEBHOOK_URL}'`
  这类非法值初始化通知渠道并抛错。现解析为空串，未配置渠道可正确跳过。
- **修复 LLM 未配置导致全流程中断**：LLM 客户端初始化失败会直接终止整个程序，
  使纯技术面分析也无法产出。现降级为警告，跳过 AI 研判后继续完成分析与报告。
- **修复通知渠道配置错误中断分析**：任一渠道构造异常都会让程序在分析完成后崩溃。
  现单渠道失败仅禁用该渠道。
- **修复新闻文章缺失字段引发 KeyError**：`news_sentiment.py` 与 `news_fetcher.py`
  直接索引 `article['source']`，字段缺失时抛错并中断该品种的整轮分析。
- **修复图表中文显示为豆腐块**：新增跨平台中文字体自动探测
  （PingFang SC / Microsoft YaHei / Noto Sans CJK SC 等），并关闭
  `axes.unicode_minus` 以规避中文字体缺失 Unicode 负号的问题。
- **修复缓存命中时数据来源标记丢失**：报价 `source` 字段在走缓存路径时显示
  `unknown`。现以 sidecar 元数据文件持久化来源名，与 CSV 数据分离存放。
- **修复失效的数据源与新闻源**：
  - Stooq 已启用 JS 反爬挑战（返回验证页而非 CSV），Yahoo Finance 对部分
    地区返回 403，两者在国内网络环境下均不可用；新增新浪财经作为主数据源。
  - 凤凰网财经 RSS 已下线返回 404；新浪财经滚动 RSS 返回 200 但条目为空。
    改用东方财富（中文，实测近百条）+ WSJ Markets（英文，贵金属结算价覆盖度高）。

### 新增

- **新浪财经数据源**（`src/data_fetchers/sina_provider.py`）
  - 国内直连稳定，无需鉴权，作为默认主数据源
  - 处理 JSONP 包装与防盗链注释前缀的剥离
  - 仅声明支持已映射的贵金属品种，避免无效降级尝试
- **多数据源与自动降级**（`src/data_fetchers/`）
  - `BaseDataProvider` 统一数据源接口，内置标准化、重采样、报价构造
  - `SinaProvider`（主源）、`StooqProvider`、`YahooProvider`（备源）
  - `MarketDataClient` 负责优先级调度；主源失败自动切备源，
    全部失败时回退本地缓存，避免单点故障导致整个流程停摆
  - 本地磁盘缓存层，默认 TTL 1 小时，支持过期缓存兜底
- **技术图表生成**（`src/reporting/chart.py`）
  - K 线 + 均线 + 布林带 + 支撑阻力位 + MACD + RSI 三面板组合图
  - 遵循国内习惯：涨红跌绿
  - matplotlib 为可选依赖，未安装时自动降级而非报错
- **信号回测与准确率追踪**（`src/analyzers/signal_tracker.py`）
  - 持久化每次趋势研判（技术面与 LLM 两路分别记录）
  - 持有期结束后回溯校验，输出胜率、盈亏比、期望收益、累计方向收益
  - 严格只使用信号时点之后的价格，杜绝前视偏差
  - 样本量不足 30 条时在报告中标注统计不显著
  - 新增 `--backtest` 参数，仅评估历史信号不做新分析
- **测试体系**（`tests/`）：覆盖技术指标、信号回测、数据源降级、
  缓存、配置加载、重试逻辑与图表生成
- **CI 流水线**（`.github/workflows/ci.yml`）：Python 3.10/3.11/3.12
  矩阵测试 + 覆盖率报告 + ruff 检查
- **重复定义静态检查**（`scripts/check_duplicates.py`）：
  在 CI 中阻断本次修复的这类回归
- 新增 `LICENSE`（MIT）与本 `CHANGELOG.md`
- 新增 `--no-chart` 参数用于禁用图表生成

### 变更

- `main.py` 改用 `MarketDataClient` 替代 `StooqClient`，
  报价数据新增 `source` 字段标识实际数据来源
- `config.yaml.example` 新增 `market_data`、`backtest` 配置段，
  `reports.include_charts` 默认改为 `true`
- 报告行情区块数值统一格式化：千分位分隔、保留两位小数、涨跌前置符号，
  并显示数据来源（此前输出 `-42.029999999999745` 这类原始浮点值）
- `requirements.txt` 新增 pytest 与 matplotlib

### 废弃

- `src/data_fetchers/stooq_client.py` 由 `StooqProvider` +
  `MarketDataClient` 取代，保留一个版本周期以兼容外部引用

## [0.1.0]

### 新增

- 基于 Stooq 的贵金属日线数据抓取，支持周/月线重采样
- MA / MACD / RSI / 布林带技术指标计算
- K 线形态识别
- 新闻抓取与情感分析
- LLM 综合研判与 Markdown 报告生成
- 飞书、钉钉、Slack、Telegram、邮件五渠道推送
- Docker 部署与 cron 定时任务
