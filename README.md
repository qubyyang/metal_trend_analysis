<div align="center">
  <h1>🤖 MetalTrend AI - 智能贵金属趋势分析系统</h1>
  <p>
    <strong>基于 AI 的自动化贵金属（黄金/白银）市场分析工具，集成 LLM 与专业技术指标，助您洞察先机。</strong>
  </p>
  <p>
    <a href="README.md">简体中文</a> | <a href="README_EN.md">English</a>
  </p>
  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
    <a href="https://github.com/qubyyang/metal_trend_analysis/stargazers"><img src="https://img.shields.io/github/stars/qubyyang/metal_trend_analysis?style=social" alt="GitHub Stars"></a>
    <a href="https://github.com/qubyyang/metal_trend_analysis/network/members"><img src="https://img.shields.io/github/forks/qubyyang/metal_trend_analysis?style=social" alt="GitHub Forks"></a>
    <img src="https://img.shields.io/badge/Maintained-Yes-green.svg" alt="Maintenance">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome">
  </p>
</div>

---

**贵金属趋势分析机器人** 是一个功能强大的 Python 工具，它整合了实时市场数据、经典技术分析以及先进的大语言模型（LLM）智能，为您提供全面、深入的黄金和白银市场洞察。分析结果将以结构化报告的形式生成，并可实时推送到飞书，让您随时随地掌握市场动态。

## 🌟 项目特色

- **🤖 AI驱动分析**: 集成GPT-4等大语言模型，生成专业市场研判和自然语言报告
- **📊 专业技术分析**: 自动计算MA、MACD、RSI、布林带、ATR等关键技术指标
- **🧮 因子化信号评分**: 六大因子加权聚合为 -100~+100 连续评分，替代信号计数投票；无效因子自动让出权重，ATR 波动率闸门动态调节置信度
- **📡 多源行情数据**: 新浪财经为主源，新浪外汇 / Stooq / Yahoo Finance 为备源，主源故障时自动降级，并带本地缓存兜底
- **🔗 跨品种联动分析**: 金银比 / 金铂比 / 金铜比，以及与美元指数、原油的滚动相关性，含 2σ 背离预警
- **📈 技术图表生成**: 自动绘制 K线+均线+布林带+支撑阻力+MACD+RSI 组合图（涨红跌绿）
- **🎯 信号准确率回测**: 历史回放回填样本，输出胜率、盈亏比、**买入持有基准对比**、显著性检验、分层胜率与衰减曲线
- **📰 新闻情感分析**: 集成Bloomberg、CNBC、凤凰网财经等新闻源，智能分析市场情绪
- **🕯️ K线形态识别**: 智能识别十多种经典K线形态（十字星、锤子线、吞噬形态等）
- **📱 多渠道推送**: 支持飞书、钉钉、Slack、Telegram、邮件通知，配置环境变量即可自动启用
- **⚙️ 高度可配置**: YAML配置文件，灵活定制分析参数和模型选择
- **📍 关键位识别**: 自动计算并标识重要的支撑位和阻力位
- **✅ 测试与CI保障**: 完整单元测试覆盖 + GitHub Actions 多版本矩阵校验

## 成果展示

下面是机器人自动生成并推送到飞书的分析报告截图：

| 每日摘要报告 (Daily Summary) | 单一品种详情报告 (Detailed Report) |
| :--------------------------: | :----------------------------: |
| <img src="images/daily_summary_report.png" alt="每日摘要报告" width="400"/> | <img src="images/detailed_report.png" alt="单个品种详细报告" width="400"/> |

## 🚀 快速开始

### Python虚拟环境安装

```bash
# 1. 克隆仓库
git clone https://github.com/qubyyang/metal_trend_analysis.git
cd metal_trend_analysis

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 复制环境变量文件
cp .env.example .env

# 5. 运行分析
python src/main.py
```

---

## 📋 详细安装步骤

### 1. 环境准备

- Python 3.10 或更高版本
- Git

### 2. 安装

```bash
# 1. 克隆仓库
git clone https://github.com/qubyyang/metal_trend_analysis.git
cd metal_trend_analysis

# 2. (推荐) 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### 3. 配置

```bash
# 1. 复制配置文件
cp config/config.yaml.example config/config.yaml

# 2. 编辑配置文件 config/config.yaml
#    填入您的 API Keys 和 Webhook URL

# 3. 编辑 .env 文件，填写环境变量
#    例如 LLM_API_KEY 等

# 4. （可选）如需本地图表渲染，可手动安装可视化依赖
# pip install matplotlib plotly
```

您需要配置以下关键信息：
- `api.stooq`: Stooq 数据源配置（无需 API Key）
- `llm.api_key`: 您选择的大语言模型提供商的 API Key
- `llm.base_url` (可选): 如果您使用代理或私有部署的 LLM，请配置此项
- `llm.model`: 指定要使用的模型名称，例如 `gpt-4-turbo`
- `feishu.webhook_url`: 飞书机器人的 Webhook 地址
- `dingtalk.webhook_url`: 钉钉机器人的 Webhook 地址（可选）
- `slack.webhook_url`: Slack 的 Webhook 地址（可选）
- `telegram.bot_token` / `telegram.chat_id`: Telegram 机器人配置（可选）
- `email.from` / `email.password` / `email.to`: 邮件通知配置（可选）
- `news.sources`: 新闻源配置（已包含Bloomberg、CNBC、凤凰网财经等已验证源）

示例 `.env`（仅示例，勿提交真实密钥）：

```env
LLM_API_KEY=your_llm_api_key
LLM_MODEL_NAME=gpt-4o
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

### 4. 运行分析

```bash
# 运行对所有已配置品种的分析
python src/main.py

# 仅分析黄金
python src/main.py --instrument gold

# 仅分析白银，并指定时间周期为 1 周
python src/main.py --instrument silver --timeframe 1w

# 跳过图表生成（加快执行速度）
python src/main.py --no-chart

# 仅回测历史信号准确率，不做新分析
python src/main.py --backtest
```

分析完成后，报告将保存在 `output/reports/` 目录下，图表保存在 `output/charts/`，同时会推送到您配置的通知渠道。

## 📡 多数据源与容错

系统按优先级依次尝试各数据源，任一环节失败自动降级到下一级：

```
新浪财经（主源） → 新浪外汇 → Stooq → Yahoo Finance → 本地缓存 → 过期缓存兜底
```

各数据源实测状态（2026-09）：

| 数据源 | 状态 | 说明 |
|--------|------|------|
| 新浪财经 | ✅ 可用 | 国内直连稳定，无需鉴权，**推荐主源** |
| 新浪外汇 | ✅ 可用 | 专用于美元指数（DXY），品种与主源不重叠 |
| Stooq | ⚠️ 受限 | 已启用 JS 反爬挑战，返回验证页而非 CSV |
| Yahoo Finance | ⚠️ 受限 | 对部分地区返回 403 |

在 `config/config.yaml` 中配置：

```yaml
market_data:
  providers: ["sina", "sina_forex", "stooq", "yahoo"]   # 数据源优先级
  cache_enabled: true
  cache_ttl: 3600                         # 缓存有效期（秒）
  allow_stale_cache: true                 # 全部数据源失效时是否用过期缓存兜底
```

报价结果中的 `source` 字段会标明本次数据的实际来源，便于排查。

> 升级提示：若你的 `config.yaml` 是旧版本、`providers` 中没有 `sina_forex`，
> 系统会自动把它补齐到通用源之前，无需手工修改即可获取美元指数数据。

### 支持的品种

品种代码于 2026-09-04 逐一实测校验，仅收录数据仍在更新的标的：

| 代码 | 品种 | 用途 |
|------|------|------|
| `XAUUSD` / `XAGUSD` | 现货黄金 / 白银 | 主分析标的 |
| `XPTUSD` / `XPDUSD` | 现货铂金 / 钯金 | 贵金属横向对比 |
| `HGUSD` | COMEX 铜 | 顺周期参照 |
| `GCUSD` / `SIUSD` | COMEX 金 / 银期货 | 期现对照 |
| `CLUSD` | NYMEX 原油 | 通胀 / 风险偏好代理 |
| `DXY` | 美元指数 | 计价货币参照 |

已确认停止更新、故意不予收录：`PL`、`PA`、`DX`（数据均停留在 2019 年）。

## 🧮 因子化信号评分

趋势判断不再依赖「看涨信号个数 vs 看跌信号个数」的简单投票，而是把六个技术因子
转换成 **[-1, +1] 的连续强度**，加权聚合为 **[-100, +100] 的综合评分**。

| 因子 | 默认权重 | 方向语义 |
|------|---------|---------|
| 均线排列 `ma_alignment` | 0.25 | 趋势跟随：多头排列为正 |
| `macd` | 0.20 | 趋势跟随：金叉 + 零轴上方为正 |
| `rsi` | 0.15 | **反转语义**：超买为负、超卖为正 |
| 布林带 `bollinger` | 0.15 | 趋势跟随：%B 越高越正 |
| 多周期共振 `multi_period` | 0.15 | 日线与周线同向给满分，背离时以周线为准并减半 |
| 成交量 `volume` | 0.10 | 放量确认价格方向 |

评分 ≥ +40 为强烈看涨，+15~+40 为看涨，-15~+15 为中性，以此类推（阈值可配置）。

三个设计要点值得说明：

1. **无效因子让出权重，而非按中性值稀释。** 新浪财经的现货金银接口 `volume`
   恒为 0（现货无集中交易所，没有统一成交量口径）。若把它当作「持续缩量」计入，
   会变成一个稳定输出负分的噪声源，系统性压低所有多头信号。引擎的做法是把该因子
   标记为 invalid，并**只用有效因子的权重做加权平均的分母**。实测黄金评分时
   有效权重为 0.90 而非 1.00，评分不受空缺影响。
2. **RSI 与布林带方向相反是刻意的。** 前者是摆动指标（超买看跌），后者按趋势跟随
   处理（贴近上轨看强）。单边行情中两者会相互抵消——这正是设计意图，
   不应由单一因子在极端行情下独断。
3. **ATR 不作为方向因子，而是波动率闸门。** 当 `ATR/收盘价` 超过阈值（默认 3%），
   对综合评分施加线性衰减（最低衰减至 50%）。这只降低置信度、不改变方向：
   波动越大，同样的技术形态越容易被噪声推翻。

报告中会输出完整的因子明细表（强度 / 权重 / 说明），结论可逐项追溯。
各因子权重、阈值均可在 `config.yaml` 的 `signal_engine` 段调整，
把某因子权重设为 `0` 即完全关闭。

评分与置信度会一并写入信号回测记录（`signal_score` / `signal_confidence`），
用于后续按「强信号 vs 弱信号」分层统计胜率，验证评分是否真有区分度。

## 🔗 跨品种联动分析

除单品种技术分析外，系统会自动计算跨品种的比价与相关性，输出独立的
`output/reports/cross_asset_*.md` 报告：

- **关键比价**：金银比、金铂比、金铜比，含日变动与近 250 日历史分位；
- **滚动相关性**：黄金~美元指数、黄金~白银、黄金~原油、白银~铜；
- **背离检测**：相关性偏离历史均值超 2σ、或与历史先验方向相反时给出提示。

```yaml
cross_asset:
  enabled: true
  auxiliary_symbols: ["XPTUSD", "HGUSD", "CLUSD", "DXY"]
  lookback_days: 400
  correlation_window: 60    # 滚动相关性窗口（交易日）
  percentile_window: 250    # 比价历史分位参考窗口
  divergence_sigma: 2.0     # 偏离多少个标准差算作背离
```

用 `--no-cross-asset` 可跳过该步骤。

> **相关性一律基于对数收益率计算**，而非价格。直接对价格序列求相关会因
> 两者的共同趋势产生伪回归，得到虚高且没有意义的相关系数。

辅助品种属可选增强：任一品种拉取失败只会跳过涉及它的指标，不影响主流程。

## 🎯 信号准确率回测

系统每次输出趋势研判时会记录一条信号（技术面与 LLM 两路分别记录）。
在持有期结束后，用实际价格回溯校验。

### 历史回填：先解决样本量问题

每天只产生一条信号，攒到统计显著（≥30 条已到期）需要数月。
回填用历史 K 线**逐日重放**，一次拿到数百条样本：

```bash
# 先预览，不写入
python src/main.py --backfill --backfill-dry-run --backfill-days 1500

# 确认无误后正式写入
python src/main.py --backfill --backfill-days 1500
```

前视偏差有三道防线：第 i 日的信号只用 `df.iloc[:i+1]` 计算；
指标全部是 `rolling`/`ewm` 因果算子（有专门的测试断言"截断重算 == 全量切片"，
若将来引入非因果指标会立刻失败）；评估端只取 `index > entry_time` 的价格。
还有一条测试直接篡改未来数据，断言历史信号评分完全不变。

**采样间隔默认等于持有期，不是逐日。** 持有期 5 日却每日采样，相邻样本的
评估窗口重叠 80%，二项检验会把标准误低估约 √5 倍——本不显著的结果看起来
p<0.01。需要更多样本应拉长历史区间，而不是缩小采样间隔。

### 运行回测

```bash
python src/main.py --backtest
```

### 真实输出（XAUUSD，2021-05 ~ 2026-08，242 条非重叠样本）

```
- 已评估信号: 242 条（胜 98 / 负 86 / 平 58）
- 胜率: 53.26%
- 盈亏比: 1.03 ｜ 单次期望收益: +0.11%
- 最大回撤: -23.96%

显著性检验: 与随机无显著差异（z=+0.88, p=0.3763），暂不能认定存在 alpha

| 口径     | 样本 | 胜率/上涨率 | 期望收益（5 日） |
|----------|------|------------|----------------|
| 策略择时 | 242  | 53.3%      | +0.111%        |
| 买入持有 | 1495 | 46.9%      | +0.220%        |

结论: 择时跑输买入持有 0.109%，当前信号未能创造价值，不应据此实盘
```

**这个结果是项目当前的真实状态，不是演示数据。** 53% 的胜率单看还行，
但三项检验都指向同一结论：z=0.88 达不到显著性；策略期望收益只有买入持有的一半；
强信号档（|score|≥40）胜率 53.2%，与中等档 53.5% 几乎无差异，说明评分缺乏区分度。
白银更差——强信号档胜率 46.8%，反而低于中等档的 55.6%。

保留这个负面结果而不是调参调到好看，是因为回测的价值在于证伪。

### 因子权重与持有期调优验证（已完成，结论：不调参）

按"因子 IC 检验 → 有效因子才进入权重优化 → 样本外验证"的顺序做了完整验证
（`python scripts/tune_verify.py`，完整报告见 [docs/因子调优验证报告.md](docs/因子调优验证报告.md)）：

1. **因子 IC 全部不达标**——黄金六因子 |IC| 均 < 0.09，白银多数为负。
   业界 |IC| < 0.03 视同噪声，没有一个因子过门槛。
2. **权重不是可调的杠杆**——等权与当前权重 IC 差 0.002；样本内网格搜索出的
   最优权重（rsi 独占）在样本外全面翻负（IS +0.124 → OOS -0.079），典型过拟合。
3. **样本外看似变好是 beta 不是 alpha**——OOS 区间黄金 +82%、白银 +141%，
   单边暴涨期任何偏多指标都会与前瞻收益正相关。
4. **滚动窗口给出相反答案**——滚动 1 年 IC（20d 持有）黄金均值 **-0.269**、
   白银 **-0.246**，9 个窗口中 7-8 个为负。整段 OOS 的 +0.21 是辛普森悖论：
   跨窗口的水平漂移制造了虚假正相关，窗口内的负号才是真实预测方向。

据此**不调整默认权重、不延长持有期、不做白银反转**。
现有六因子全是价格衍生指标、在贵金属上高度共线，出路是引入正交信息源
（实际利率、ETF 持仓、COMEX 库存、美元指数），而不是在同一批价格数据上重新配比。

**信号引擎的定位据此修订：它是可复现、可审计、无前视偏差的纪律框架，
分数本身当前不构成入场依据。**

### 报告包含的维度

| 维度 | 作用 |
|------|------|
| 胜率 / 盈亏比 / 期望收益 | 基础表现 |
| **买入持有基准对比** | 区分 alpha 与 beta——牛市里只喊多也有 55% 胜率 |
| **二项显著性检验** | 样本 ≥30 时给出 z 值与 p 值，否则明确标注样本不足 |
| **按信号强度分层胜率** | 强信号胜率若不高于弱信号，说明评分是噪声的重新包装 |
| **持有期衰减曲线** | 1/3/5/10/20 日各自的胜率，判断信号捕捉的是动量还是趋势 |
| 最大回撤 | 信号序列等权累计的连续失误深度（非真实账户回撤） |

### 配置项

```yaml
backtest:
  horizon_days: 5      # 信号持有期（自然日）
  threshold_pct: 0.5   # 有效方向变动的最小幅度，低于此值计为“平”

backfill:
  warmup_bars: 120     # 前置预热根数，保证 MA60/MACD 已稳定
  # step_bars: 5       # 采样间隔，留空则等于 horizon_days
```

### 每日自动采集

```bash
# cron：每个交易日 06:30 采集，周一额外跑一次回测
30 6 * * 1-5 /path/to/metal_trend_analysis/scripts/daily_signal_cron.sh
```

macOS 推荐用 `scripts/com.metaltrend.daily.plist`（launchd）而非 cron：
机器休眠错过的任务，唤醒后会补跑，而 cron 会直接跳过——漏掉的那天就是永久缺失的样本。


## 🧪 测试

```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行全部测试
pytest -v

# 查看覆盖率
pytest --cov=src --cov-report=term-missing

# 检查重复定义（CI 中会自动执行）
python scripts/check_duplicates.py
```

## 🐳 Docker 部署

MetalTrend AI 提供了 Docker 部署方案，支持一键启动和定时任务。

### 快速启动

```bash
# 1. 复制环境变量配置
cp .env.example .env

# 2. 编辑 .env 文件，填入 API 密钥
vim .env

# 3. 启动容器
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

> 提示：容器内默认读取 `config/config.yaml`，请确保已复制并配置该文件。

### 单次执行（不使用定时）

```bash
# 运行一次后退出
docker-compose run --rm -e CRON_SCHEDULE= metal-trend-analysis

# 指定品种与周期
docker-compose run --rm -e CRON_SCHEDULE= -e INSTRUMENT=gold -e TIMEFRAME=1h metal-trend-analysis
```

### 定时执行

通过环境变量 `CRON_SCHEDULE` 配置定时分析：

```bash
# 每天早上 9 点执行
docker-compose run -e CRON_SCHEDULE="0 9 * * *" metal-trend-analysis

# 每小时执行一次
docker-compose run -e CRON_SCHEDULE="0 * * * *" metal-trend-analysis

# 自定义时区（可选）
docker-compose run -e CRON_SCHEDULE="0 9 * * *" -e TZ=Asia/Shanghai metal-trend-analysis
```

### 常用操作

```bash
# 停止并移除容器
docker-compose down

# 重新构建镜像
docker-compose up -d --build

# 查看 cron 日志（容器内）
docker-compose exec metal-trend-analysis tail -f /app/output/logs/cron.log
```

详细说明请参考 [SETUP.md](SETUP.md#docker-部署推荐)

## 📰 新闻情感分析功能

MetalTrend AI现在集成了强大的新闻情感分析功能，可以从多个权威新闻源抓取相关新闻，并自动分析市场情绪。

### 🏢 支持的新闻源

目前系统内置以下已验证可用的新闻源：

#### 英文新闻源
- **Bloomberg Markets** - 全球领先的商业和金融市场信息提供商
- **CNBC Market News** - 美国商业新闻权威机构

#### 中文新闻源  
- **凤凰网财经** - 知名中文财经媒体
- **华尔街见闻** - 重要财经资讯平台
- **财联社电报** - 财经快讯与市场电报
- **澎湃新闻** - 综合新闻与财经报道

> 说明：部分源使用 **HTML 解析 + Jina AI 文本代理**，用于解决无公开 RSS 的站点。

### 🔧 工作原理

1. **新闻抓取**：系统从配置的 RSS / HTML / API 源定时抓取最新新闻
2. **关键词过滤**：根据`config/keywords.txt`中的关键词筛选相关新闻
3. **情感分析**：使用内置的情感词典分析每篇新闻的积极/消极词汇
4. **综合研判**：结合技术面分析，提供全面的市场洞察

### ⚙️ 配置说明

在`config/config.yaml`中，您可以配置以下新闻相关选项：

```yaml
news:
  enabled: true  # 启用新闻抓取
  max_articles: 10  # 每个源最多抓取的文章数
  cache_duration: 300  # 缓存时长（秒，5分钟）
  fetch:
    timeout: 15
    delay: 2  # 不同源之间的请求延迟（秒）
    max_retries: 3
  sources:
    # 可根据需要启用或禁用不同新闻源
    - name: "Bloomberg Markets"
      type: "rss"
      url: "https://feeds.bloomberg.com/markets/news.rss"
      enabled: true
    - name: "华尔街见闻"
      type: "html"
      url: "https://r.jina.ai/http://wallstreetcn.com/"
      parser: "markdown_links"
      link_contains:
        - "wallstreetcn.com/articles"
        - "wallstreetcn.com/livenews"
      enabled: true
    # ... 其他新闻源配置
```

### 📊 分析报告集成

新闻情感分析结果会集成到最终的Markdown报告中：
- **新闻情感统计**：显示整体市场情绪倾向
- **关键主题识别**：提取高频的积极/消极词汇
- **代表性文章**：展示最具影响力的新闻
- **LLM深度分析**：结合新闻内容提供专业的市场研判

### ✅ 新闻源测试

如需验证新闻源可用性，可运行测试脚本：

```bash
python scripts/check_news_sources.py
```

默认读取 `config/config.yaml`，若不存在则读取 `config/config.yaml.example`。

## 📁 项目结构

```
metal_trend_analysis/
├── config/                # 配置文件
│   ├── config.yaml        # 主配置文件
│   └── keywords.txt       # 新闻关键词
├── data/                  # 原始数据与缓存
├── docker/                # Docker 相关脚本
├── docs/                  # 内部文档
│   └── internal/
├── images/                # README 和报告中使用的图片
├── output/                # 程序输出
│   ├── logs/              # 日志文件
│   ├── charts/            # 生成的技术图表
│   └── reports/           # 生成的 Markdown 报告
├── scripts/               # 辅助脚本
│   ├── check_duplicates.py # 重复定义静态检查
│   └── check_news_sources.py
├── tests/                 # ✅ 单元测试
├── src/                   # 核心源代码
│   ├── main.py            # 🚀 主程序入口
│   ├── analyzers/         # 📊 分析模块 (技术指标, K线形态, 新闻情感, 信号回测, 跨品种联动)
│   ├── data_fetchers/     # 📡 数据获取模块 (多源行情, 降级调度, 新闻抓取)
│   ├── llm/               # 🤖 LLM 分析模块
│   ├── notification/      # 📢 通知模块 (飞书/钉钉/Slack/Telegram/邮件)
│   ├── reporting/         # 📄 报告与图表生成模块
│   └── utils/             # 🛠️ 工具类 (配置加载, 日志)
├── .github/workflows/     # CI 流水线
├── docker-compose.yml     # Docker Compose 配置
├── Dockerfile             # Docker 镜像构建
├── .gitignore
├── CHANGELOG.md           # 变更日志
├── LICENSE
├── README.md              # 本文档
├── README_EN.md           # English README
└── requirements.txt       # Python 依赖
```

## 🏗️ 系统架构

MetalTrend AI 采用模块化架构设计，各组件职责清晰，易于扩展和维护。

### 核心模块说明

1. **数据获取模块** (`data_fetchers/`)
   - `BaseDataProvider` 统一数据源接口，内置标准化与重采样
   - 新浪财经主源 + 新浪外汇 / Stooq / Yahoo Finance 备源，失败自动降级
   - 本地磁盘缓存，全部数据源失效时可用过期缓存兜底

2. **分析引擎** (`analyzers/`)
   - 技术指标计算（MA、MACD、RSI、布林带、ATR）
   - K线形态识别（十字星、锤子线、吞噬形态等）
   - 新闻情感分析（市场情绪量化评估）
   - 趋势研判和关键位识别
   - 信号追踪与准确率回测（无前视偏差）
   - 跨品种比价与滚动相关性（基于对数收益率，含背离检测）

3. **LLM分析模块** (`llm/`)
   - 集成GPT系列大语言模型
   - 生成自然语言市场分析报告
   - 支持自定义prompt和模型选择

4. **报告生成** (`reporting/`)
   - 自动生成Markdown格式报告
   - 包含图表、指标表格和AI分析结论
   - 支持多种输出格式

5. **通知系统** (`notification/`)
  - 飞书/钉钉/Slack/Telegram/邮件通知
  - 基于环境变量自动启用
  - 推送失败重试机制

## 🗺️ 发展路线图

### ✅ 已完成 - v1.0
- [x] Stooq 免费数据获取
- [x] 技术指标计算（MA、MACD、RSI、布林带）
- [x] K线形态识别（10+种经典形态）
- [x] LLM分析集成（GPT-4支持）
- [x] 自动报告生成（Markdown格式）
- [x] 飞书通知功能
- [x] 新闻抓取与情感分析（集成Bloomberg、CNBC、凤凰网财经等已验证源）

### ✅ 已完成 - v1.1
- [x] Docker一键部署（支持定时任务，默认时区Asia/Shanghai）

### 🚧 计划中 - v1.2
- [ ] 配置向导
- [ ] 错误处理优化
- [ ] 单元测试覆盖
- [ ] CI/CD流程
- [ ] Web界面（Streamlit）
- [ ] 更多技术指标（KDJ、OBV等）
- [ ] 自定义交易策略支持
- [ ] 历史数据回测功能

### 🎯 未来规划 - v2.0
- [ ] 机器学习模型集成
- [ ] 多交易所数据支持
- [ ] 移动端APP
- [ ] 社区策略分享平台
- [ ] 实时交易信号推送

---

## 📊 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.10+ |
| **数据处理** | Pandas, NumPy |
| **LLM/AI** | OpenAI 兼容 API（OpenAI / DeepSeek / Qwen） |
| **技术分析** | 自研指标计算（Pandas / NumPy） |
| **可视化** | Matplotlib, Plotly（可选） |
| **API** | 新浪财经 / Stooq / Yahoo Finance (free), Feishu / DingTalk / Slack / Telegram / Email |

---

## 🤝 贡献指南

我们热烈欢迎任何形式的贡献！无论是功能建议、代码优化、Bug 修复还是文档改进，都对我们至关重要。

### 如何贡献

1. **Fork 本仓库**
2. **创建特性分支** (`git checkout -b feature/AmazingFeature`)
3. **提交更改** (`git commit -m 'Add some AmazingFeature'`)
4. **推送分支** (`git push origin feature/AmazingFeature`)
5. **开启 Pull Request**

请参考 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细的贡献流程和代码规范。

## 📄 开源许可

本项目基于 [MIT License](LICENSE) 开源。

---

## 📚 相关资源

- [项目文档（内部）](docs/internal/)

## 🌟 社区与支持

- **GitHub Issues**: 报告Bug或提出新功能

---

## 🏷️ 相关标签

```
gold, silver, trading, technical-analysis, llm, gpt,
precious-metals, quantitative-finance, ai, python,
trend-analysis, market-analysis, algorithmic-trading,
chatgpt, open-source, fin-tech
```

---

## ⚠️ 免责声明

本工具提供的所有分析、数据和报告仅供学习和研究使用，不构成任何投资建议。金融市场存在风险，任何基于本工具信息进行的投资决策，风险自负。

---

<div align="center">
  <h3>🙏 如果这个项目对您有帮助，请给一个 ⭐️ Star！</h3>
  <p>您的支持是我们持续优化的动力 💪</p>
  <p>
    <a href="https://github.com/qubyyang/metal_trend_analysis">
      <img src="https://img.shields.io/badge/GitHub-MetalTrend%20AI-blue?logo=github" alt="GitHub">
    </a>
  </p>
</div>
