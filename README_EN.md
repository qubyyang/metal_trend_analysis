<div align="center">
  <h1>🤖 MetalTrend AI - Intelligent Precious Metals Trend Analysis System</h1>
  <p>
    <strong>AI-powered automated precious metals (gold/silver) market analysis tool, integrating LLM and professional technical indicators to help you seize opportunities.</strong>
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

**MetalTrend AI** is a powerful Python tool that integrates real-time market data, classical technical analysis, and advanced Large Language Model (LLM) intelligence to provide comprehensive, in-depth insights into gold and silver markets. Analysis results are generated as structured reports and can be pushed to Feishu in real-time, allowing you to stay informed about market dynamics anytime, anywhere.

## 🌟 Key Features

- **🤖 AI-Driven Analysis**: Integrates GPT-4 and other large language models to generate professional market analysis and natural language reports
- **📊 Professional Technical Analysis**: Automatically calculates key technical indicators including MA, MACD, RSI, Bollinger Bands, and more
- **📡 Real-Time Data**: Connects to iTick API for millisecond-level market updates, ensuring data freshness
- **🕯️ Candlestick Pattern Recognition**: Intelligently identifies 10+ classic candlestick patterns (Doji, Hammer, Engulfing, etc.)
- **📱 Multi-Channel Notifications**: Supports Feishu, email, and other notification methods to ensure timely information delivery
- **⚙️ Highly Configurable**: All parameters (API keys, model selection, notification channels, etc.) are configured via YAML files for flexibility
- **🎯 Intelligent Trend Analysis**: Combines multiple indicators to automatically determine market trends (bullish/bearish/ranging)
- **📍 Key Level Identification**: Automatically calculates and identifies important support and resistance levels

---

## 📸 Showcase

Below are screenshots of analysis reports automatically generated and pushed to Feishu:

| Daily Summary Report | Detailed Single Instrument Report |
| :------------------: | :-------------------------------: |
| <img src="images/daily_summary_report.png" alt="Daily Summary Report" width="400"/> | <img src="images/detailed_report.png" alt="Single Instrument Detailed Report" width="400"/> |

---

## 🚀 Quick Start

### Python Virtual Environment Installation

```bash
# 1. Clone the repository
git clone https://github.com/qubyyang/metal_trend_analysis.git
cd metal_trend_analysis

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run analysis
python src/main.py
```

---

## 📋 Detailed Installation Steps

### 1. Prerequisites

- Python 3.10 or higher
- Git

### 2. Install

```bash
# 1. Clone the repository
git clone https://github.com/qubyyang/metal_trend_analysis.git
cd metal_trend_analysis

# 2. (Recommended) Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# 1. Copy configuration file
cp config/config.yaml.example config/config.yaml

# 2. Edit config/config.yaml
#    Fill in your API Keys and Webhook URL
```

You need to configure the following key information:
- `itick.token`: iTick API access token
- `llm.api_key`: Your LLM provider's API key
- `llm.base_url` (optional): Configure this if you use a proxy or self-hosted LLM
- `llm.model`: Specify the model name, e.g., `gpt-4-turbo`
- `feishu.webhook_url`: Feishu bot's webhook URL

### 4. Run Analysis

```bash
# Run analysis on all configured instruments
python src/main.py

# Analyze only gold
python src/main.py --instrument gold

# Analyze only silver with 1-hour timeframe
python src/main.py --instrument silver --timeframe 1h
```

After analysis is complete, reports will be saved in the `output/reports/` directory and pushed to your configured Feishu channel.

---

## 📁 Project Structure

```
metal_trend_analysis/
├── config/                # Configuration files
│   ├── config.yaml        # Main configuration file
│   └── keywords.txt       # (Not used yet) News keywords
├── data/                  # Raw data and cache
├── docs/                  # Project documentation
├── images/                # Images for README and reports
├── output/                # Program output
│   ├── logs/              # Log files
│   └── reports/           # Generated Markdown reports
├── src/                   # Core source code
│   ├── main.py            # 🚀 Main entry point
│   ├── analyzers/         # 📊 Analysis modules (indicators, candlestick patterns)
│   ├── data_fetchers/     # 📡 Data fetching modules (iTick)
│   ├── llm/               # 🤖 LLM analysis modules
│   ├── notification/      # 📢 Notification modules (Feishu)
│   ├── reporting/         # 📄 Report generation modules
│   └── utils/             # 🛠️ Utility classes (config loading, logging)
├── .github/               # GitHub configuration
│   ├── workflows/         # GitHub Actions
│   └── ISSUE_TEMPLATE/    # Issue templates
├── examples/              # Example code
├── tests/                 # Unit tests
├── .gitignore
├── LICENSE
├── README.md              # This document (Chinese)
├── README_EN.md           # This document (English)
└── requirements.txt       # Python dependencies
```

## 🏗️ System Architecture

MetalTrend AI adopts a modular architecture design with clear responsibilities for each component, making it easy to extend and maintain.

### Core Module Descriptions

1. **Data Fetching Module** (`data_fetchers/`)
   - Connects to iTick API for real-time market data
   - Supports multiple timeframe K-line data
   - Built-in data caching mechanism to reduce API calls

2. **Analysis Engine** (`analyzers/`)
   - Technical indicator calculations (MA, MACD, RSI, Bollinger Bands, etc.)
   - Candlestick pattern recognition (Doji, Hammer, Engulfing, etc.)
   - Trend analysis and key level identification

3. **LLM Analysis Module** (`llm/`)
   - Integrates GPT series large language models
   - Generates natural language market analysis reports
   - Supports custom prompts and model selection

4. **Report Generation** (`reporting/`)
   - Automatically generates Markdown format reports
   - Includes charts, indicator tables, and AI analysis conclusions
   - Supports multiple output formats

5. **Notification System** (`notification/`)
   - Feishu bot integration
   - Email notifications (coming soon)
   - Push failure retry mechanism

---

## 🗺️ Roadmap

### ✅ Completed - v1.0
- [x] iTick API data fetching
- [x] Technical indicator calculations (MA, MACD, RSI, Bollinger Bands)
- [x] Candlestick pattern recognition (10+ classic patterns)
- [x] LLM analysis integration (GPT-4 support)
- [x] Automatic report generation (Markdown format)
- [x] Feishu notification functionality

### 🚧 In Progress - v1.1
- [ ] Docker one-click deployment
- [ ] Configuration wizard
- [ ] Error handling optimization
- [ ] Unit test coverage
- [ ] CI/CD pipeline

### 📅 Planned - v1.2
- [ ] Web interface (Streamlit)
- [ ] More technical indicators (KDJ, OBV, etc.)
- [ ] Custom trading strategy support
- [ ] Historical data backtesting
- [ ] Email notification support

### 🎯 Future Plans - v2.0
- [ ] Machine learning model integration
- [ ] Multi-exchange data support
- [ ] Mobile app
- [ ] Community strategy sharing platform
- [ ] Real-time trading signal push

---

## 📊 Tech Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.10+ |
| **Data Processing** | Pandas, NumPy |
| **Machine Learning** | OpenAI API, LangChain |
| **Technical Analysis** | TA-Lib, Pandas TA |
| **Visualization** | Matplotlib, Plotly |
| **API** | iTick API, Feishu API |

---

## 🤝 Contributing

We welcome all forms of contributions! Whether it's feature suggestions, code optimizations, bug fixes, or documentation improvements, they are all valuable to us.

### How to Contribute

1. **Fork this repository**
2. **Create a feature branch** (`git checkout -b feature/AmazingFeature`)
3. **Commit your changes** (`git commit -m 'Add some AmazingFeature'`)
4. **Push to the branch** (`git push origin feature/AmazingFeature`)
5. **Open a Pull Request**

Please refer to [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines and code standards.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 📚 Related Resources

- [Project Documentation](docs/)
- [Example Code](examples/)
- [API Documentation](docs/api/)
- [FAQ](docs/faq.md)

## 🌟 Community & Support

- **GitHub Issues**: Report bugs or suggest new features
- **GitHub Discussions**: Technical discussions and Q&A
- **Discord Community**: Real-time communication and sharing (coming soon)

---

## 🏷️ Related Tags

```
gold, silver, trading, technical-analysis, llm, gpt,
precious-metals, quantitative-finance, ai, python,
trend-analysis, market-analysis, algorithmic-trading,
chatgpt, open-source, fin-tech
```

---

## ⚠️ Disclaimer

All analysis, data, and reports provided by this tool are for learning and research purposes only and do not constitute any investment advice. Financial markets carry risks, and you are solely responsible for any investment decisions made based on information from this tool.

---

<div align="center">
  <h3>🙏 If this project helps you, please give it a ⭐️ Star!</h3>
  <p>Your support motivates us to keep improving 💪</p>
  <p>
    <a href="https://github.com/qubyyang/metal_trend_analysis">
      <img src="https://img.shields.io/badge/GitHub-MetalTrend%20AI-blue?logo=github" alt="GitHub">
    </a>
  </p>
</div>
