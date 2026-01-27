<div align="center">
  <h1>贵金属趋势分析机器人</h1>
  <p>
    <strong>一个基于 AI 的自动化贵金属（黄金/白银）市场分析工具，助您洞察先机。</strong>
  </p>
  <p>
    <a href="README.md">简体中文</a> | <a href="README_EN.md">English</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/Status-✅%20Active-green.svg" alt="Status Active">
  </p>
</div>

---

**贵金属趋势分析机器人** 是一个功能强大的 Python 工具，它整合了实时市场数据、经典技术分析以及先进的大语言模型（LLM）智能，为您提供全面、深入的黄金和白银市场洞察。分析结果将以结构化报告的形式生成，并可实时推送到飞书，让您随时随地掌握市场动态。

## ✨ 核心功能

- **📈 实时行情获取**: 对接 iTick API，获取毫秒级更新的贵金属实时报价和 K 线数据。
- **📊 专业技术分析**:
  - **多指标计算**: 自动计算 MA, MACD, RSI, 布林带等关键技术指标。
  - **趋势智能研判**: 结合多指标分析，判断当前市场趋势（看涨/看跌/震荡）。
  - **关键位识别**: 自动识别并计算重要的支撑位和阻力位。
- **🕯️ K线形态识别**: 自动识别十多种经典 K 线形态，如“十字星”、“锤子线”、“吞噬形态”等，洞察市场反转或持续信号。
- **🤖 LLM 智能分析**:
  - **综合研判**: 利用大语言模型（如 GPT 系列）的强大能力，结合行情数据和技术指标，生成对市场趋势、风险等级和交易策略的综合分析。
  - **自然语言报告**: 将复杂的分析结果转化为通俗易懂的自然语言结论和操作建议。
- **📄 自动化报告**: 一键生成结构清晰、内容详实的 Markdown 分析报告，方便复盘和分享。
- **🚀 飞书实时推送**: 将分析报告（包括图表和摘要）实时推送到您的飞书群组，确保信息及时触达。
- **⚙️ 高度可配置**: 所有参数（API密钥、模型选择、通知渠道等）均通过 YAML 文件进行配置，灵活易用。

## 成果展示

下面是机器人自动生成并推送到飞书的分析报告截图：

| 每日摘要报告 (Daily Summary) | 单一品种详情报告 (Detailed Report) |
| :--------------------------: | :----------------------------: |
| <img src="images/daily_summary_report.png" alt="每日摘要报告" width="400"/> | <img src="images/detailed_report.png" alt="单个品种详细报告" width="400"/> |

## 🚀 快速开始

仅需几步，即可启动您的专属市场分析机器人。

### 1. 环境准备

- Python 3.10 或更高版本
- Git

### 2. 克隆与安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/metal_trend_analysis.git
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
```

您需要配置以下关键信息：
- `itick.token`: iTick API 的访问令牌。
- `llm.api_key`: 您选择的大语言模型提供商的 API Key。
- `llm.base_url` (可选): 如果您使用代理或私有部署的 LLM，请配置此项。
- `llm.model`: 指定要使用的模型名称，例如 `gpt-4-turbo`。
- `feishu.webhook_url`: 飞书机器人的 Webhook 地址。

### 4. 运行分析

```bash
# 运行对所有已配置品种的分析
python src/main.py

# 仅分析黄金
python src/main.py --instrument gold

# 仅分析白银，并指定时间周期为 1 小时
python src/main.py --instrument silver --timeframe 1h
```

分析完成后，报告将保存在 `output/reports/` 目录下，同时会推送到您配置的飞书频道。

## 📁 项目结构

```
metal_trend_analysis/
├── config/                # 配置文件
│   ├── config.yaml        # 主配置文件
│   └── keywords.txt       # (暂未使用) 新闻关键词
├── data/                  # 原始数据和缓存
├── docs/                  # 项目文档
├── images/                # README 和报告中使用的图片
├── output/                # 程序输出
│   ├── logs/              # 日志文件
│   └── reports/           # 生成的 Markdown 报告
├── src/                   # 核心源代码
│   ├── main.py            # 🚀 主程序入口
│   ├── analyzers/         # 📊 分析模块 (技术指标, K线形态)
│   ├── data_fetchers/     # 📡 数据获取模块 (iTick)
│   ├── llm/               # 🤖 LLM 分析模块
│   ├── notification/      # 📢 通知模块 (飞书)
│   ├── reporting/         # 📄 报告生成模块
│   └── utils/             # 🛠️ 工具类 (配置加载, 日志)
├── .gitignore
├── README.md              # 本文档
└── requirements.txt       # Python 依赖
```

## 🤝 贡献指南

我们热烈欢迎任何形式的贡献！无论是功能建议、代码优化、Bug 修复还是文档改进，都对我们至关重要。

请参考 [CONTRIBUTING.md](CONTRIBUTING.md)（待创建）了解详细的贡献流程。

## 📄 开源许可

本项目基于 [MIT License](LICENSE) 开源。

## ⚠️ 免责声明

本工具提供的所有分析、数据和报告仅供学习和研究使用，不构成任何投资建议。金融市场存在风险，任何基于本工具信息进行的投资决策，风险自负。

---

<div align="center">
  <strong>如果这个项目对您有帮助，请给一个 ⭐️ Star！</strong>
</div>
