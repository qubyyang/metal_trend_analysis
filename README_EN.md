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
- **📊 Professional Technical Analysis**: Automatically calculates key technical indicators including MA, MACD, RSI, Bollinger Bands, ATR, and more
- **🧮 Factor-Based Signal Scoring**: Six weighted factors aggregate into a continuous -100~+100 score, replacing signal-count voting; invalid factors release their weight, and an ATR volatility gate modulates confidence
- **📡 Multi-Source Market Data**: Sina Finance as primary with Sina Forex / Stooq / Yahoo Finance failover, plus local cache fallback for resilience
- **🔗 Cross-Asset Analysis**: Gold/silver, gold/platinum and gold/copper ratios plus rolling correlations against the Dollar Index and crude oil, with 2σ divergence alerts
- **📈 Technical Chart Generation**: Renders candlestick + MA + Bollinger Bands + support/resistance + MACD + RSI composite charts
- **🎯 Signal Accuracy Backtesting**: Historical replay for sample bootstrapping, reporting win rate, profit factor, **buy-and-hold benchmark**, significance testing, stratified win rates and decay curves
- **📰 News Sentiment Analysis**: Integrates Bloomberg, CNBC, Phoenix Finance and other news sources for intelligent market sentiment analysis
- **🕯️ Candlestick Pattern Recognition**: Intelligently identifies 10+ classic candlestick patterns (Doji, Hammer, Engulfing, etc.)
- **📱 Multi-Channel Notifications**: Supports Feishu, DingTalk, Slack, Telegram, and Email. Channels auto-enable based on environment variables
- **⚙️ Highly Configurable**: All parameters (API keys, model selection, notification channels, etc.) are configured via YAML files for flexibility
- **📍 Key Level Identification**: Automatically calculates and identifies important support and resistance levels
- **✅ Tested & CI-Backed**: Full unit test suite with GitHub Actions matrix validation

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

# 4. Copy environment file
cp .env.example .env

# 5. Run analysis
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

# 3. Edit .env and fill in environment variables
#    e.g., LLM_API_KEY

# 4. (Optional) Install visualization dependencies if you need charts
# pip install matplotlib plotly
```

You need to configure the following key information:
- `api.stooq`: Stooq data source settings (no API key required)
- `llm.api_key`: Your LLM provider's API key
- `llm.base_url` (optional): Configure this if you use a proxy or self-hosted LLM
- `llm.model`: Specify the model name, e.g., `gpt-4-turbo`
- `feishu.webhook_url`: Feishu bot webhook URL
- `dingtalk.webhook_url`: DingTalk bot webhook URL (optional)
- `slack.webhook_url`: Slack webhook URL (optional)
- `telegram.bot_token` / `telegram.chat_id`: Telegram bot credentials (optional)
- `email.from` / `email.password` / `email.to`: Email notification credentials (optional)
- `news.sources`: News source configuration (includes verified sources: Bloomberg, CNBC, Phoenix Finance, etc.)

Example `.env` (for reference only, never commit real secrets):

```env
LLM_API_KEY=your_llm_api_key
LLM_MODEL_NAME=gpt-4o
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

### 4. Run Analysis

```bash
# Run analysis on all configured instruments
python src/main.py

# Analyze only gold
python src/main.py --instrument gold

# Analyze only silver with weekly timeframe
python src/main.py --instrument silver --timeframe 1w

# Skip chart generation for faster runs
python src/main.py --no-chart

# Backtest historical signal accuracy only
python src/main.py --backtest
```

After analysis is complete, reports are saved in `output/reports/`, charts in `output/charts/`, and pushed to your configured notification channels.

## 📡 Multi-Source Data & Failover

The system tries each data source in priority order, degrading automatically on failure:

```
Sina Finance (primary) → Sina Forex → Stooq → Yahoo Finance → local cache → stale cache fallback
```

Measured source availability (Sept 2026):

| Source | Status | Notes |
|--------|--------|-------|
| Sina Finance | ✅ Available | Stable direct access, no auth required, **recommended primary** |
| Sina Forex | ✅ Available | Dedicated to the Dollar Index (DXY); symbol set does not overlap the primary |
| Stooq | ⚠️ Restricted | Now serves a JS anti-bot challenge page instead of CSV |
| Yahoo Finance | ⚠️ Restricted | Returns 403 in some regions |

Configure in `config/config.yaml`:

```yaml
market_data:
  providers: ["sina", "sina_forex", "stooq", "yahoo"]   # source priority
  cache_enabled: true
  cache_ttl: 3600                         # cache lifetime in seconds
  allow_stale_cache: true                 # use expired cache when all sources fail
```

The `source` field in quote data indicates which provider actually served the request.

> Upgrade note: if your existing `config.yaml` predates `sina_forex` and omits it
> from `providers`, the client inserts it automatically ahead of the generic
> sources — no manual edit is needed to fetch Dollar Index data.

### Supported Instruments

Every symbol code was individually verified against the live API on 2026-09-04.
Only instruments with actively updating data are included:

| Code | Instrument | Purpose |
|------|-----------|---------|
| `XAUUSD` / `XAGUSD` | Spot gold / silver | Primary analysis targets |
| `XPTUSD` / `XPDUSD` | Spot platinum / palladium | Precious-metal cross comparison |
| `HGUSD` | COMEX copper | Pro-cyclical reference |
| `GCUSD` / `SIUSD` | COMEX gold / silver futures | Spot-futures comparison |
| `CLUSD` | NYMEX crude oil | Inflation / risk-appetite proxy |
| `DXY` | US Dollar Index | Pricing-currency reference |

Deliberately excluded as confirmed stale: `PL`, `PA`, `DX` — all frozen since 2019.

## 🧮 Factor-Based Signal Scoring

Trend determination no longer relies on a naive "count bullish vs. count bearish" vote.
Six technical factors are converted into **continuous strengths in [-1, +1]** and
aggregated by weight into a **composite score in [-100, +100]**.

| Factor | Default Weight | Directional Semantics |
|--------|---------------|----------------------|
| `ma_alignment` | 0.25 | Trend-following: bullish alignment is positive |
| `macd` | 0.20 | Trend-following: golden cross above zero axis is positive |
| `rsi` | 0.15 | **Reversal**: overbought is negative, oversold is positive |
| `bollinger` | 0.15 | Trend-following: higher %B is more positive |
| `multi_period` | 0.15 | Daily/weekly resonance scores full; on divergence the weekly direction wins at half strength |
| `volume` | 0.10 | Expansion confirms the price direction |

Score ≥ +40 is strong bullish, +15 to +40 bullish, -15 to +15 neutral, and so on
(thresholds are configurable).

Three design decisions worth calling out:

1. **Invalid factors release their weight rather than diluting toward neutral.**
   Sina Finance's spot gold/silver endpoints return `volume` as a constant 0 (spot
   metals have no centralized exchange, hence no unified volume convention). Treating
   that as "persistent contraction" would turn the factor into a noise source that
   steadily emits negative scores and systematically suppresses every bullish signal.
   The engine marks the factor invalid and uses **only valid-factor weights as the
   denominator** of the weighted average. In a live gold run the effective weight was
   0.90 rather than 1.00, and the score was unaffected by the gap.
2. **RSI and Bollinger point in opposite directions on purpose.** The former is an
   oscillator (overbought → bearish); the latter is treated as trend-following (riding
   the upper band → strong). In one-sided markets they partially cancel — that is the
   intent. No single factor should dictate the call at extremes.
3. **ATR is a volatility gate, not a directional factor.** When `ATR/close` exceeds the
   threshold (3% by default), the composite score is damped linearly (down to 50%).
   This lowers confidence without changing direction: the higher the volatility, the
   more easily the same technical setup is overturned by noise.

Reports include a full factor breakdown (strength / weight / rationale), making every
conclusion traceable. Weights and thresholds live under the `signal_engine` section of
`config.yaml`; setting a factor's weight to `0` disables it entirely.

Score and confidence are persisted alongside each backtest record (`signal_score` /
`signal_confidence`), enabling later win-rate stratification by "strong vs. weak signal"
to verify the score actually discriminates.

## 🔗 Cross-Asset Analysis

Beyond per-instrument technical analysis, the system computes cross-asset ratios
and correlations, emitting a standalone `output/reports/cross_asset_*.md` report:

- **Key ratios**: gold/silver, gold/platinum, gold/copper — with daily change and
  percentile rank over the trailing 250 sessions;
- **Rolling correlations**: gold~DXY, gold~silver, gold~crude, silver~copper;
- **Divergence detection**: flags correlations deviating more than 2σ from their
  historical mean, or inverting relative to the historical prior.

```yaml
cross_asset:
  enabled: true
  auxiliary_symbols: ["XPTUSD", "HGUSD", "CLUSD", "DXY"]
  lookback_days: 400
  correlation_window: 60    # rolling correlation window (trading days)
  percentile_window: 250    # lookback for ratio percentile ranking
  divergence_sigma: 2.0     # deviation threshold in standard deviations
```

Pass `--no-cross-asset` to skip this stage.

> **Correlations are always computed on log returns**, never on prices. Correlating
> raw price series yields spurious regression driven by shared trend, producing
> inflated and meaningless coefficients.

Auxiliary instruments are strictly an enhancement: if any of them fails to load,
only the metrics involving it are skipped — the main pipeline is unaffected.

## 🎯 Signal Accuracy Backtesting

Every trend call is persisted (technical and LLM tracked separately). Once the
holding period elapses, the call is verified against actual prices.

### Historical Backfill: Fixing the Sample-Size Problem

One signal per day means months of waiting before reaching statistical significance
(≥30 matured signals). Backfill **replays historical bars** to obtain hundreds of
samples at once:

```bash
# Preview without writing
python src/main.py --backfill --backfill-dry-run --backfill-days 1500

# Commit to the store
python src/main.py --backfill --backfill-days 1500
```

Three defenses against lookahead bias: day *i*'s signal is computed from
`df.iloc[:i+1]` only; all indicators are causal `rolling`/`ewm` operators (a dedicated
test asserts "truncated recompute == full-run slice", so introducing a non-causal
indicator fails immediately); and the evaluator only reads prices at
`index > entry_time`. A further test tampers with future bars and asserts historical
scores are bit-identical.

**Sampling stride defaults to the holding period, not daily.** Sampling every day with
a 5-day horizon makes adjacent evaluation windows overlap 80%, which understates the
binomial standard error by roughly √5 — insignificant results start looking like
p<0.01. Need more samples? Extend the history range, don't shrink the stride.

### Running the Backtest

```bash
python src/main.py --backtest
```

### Actual Output (XAUUSD, 2021-05 to 2026-08, 242 non-overlapping samples)

```
- Signals evaluated: 242 (98 wins / 86 losses / 58 flat)
- Win rate: 53.26%
- Profit factor: 1.03 | Expectancy: +0.11%
- Max drawdown: -23.96%

Significance: no significant difference from random (z=+0.88, p=0.3763)

| Basis        | Samples | Win/Up rate | Expectancy (5d) |
|--------------|---------|-------------|-----------------|
| Strategy     | 242     | 53.3%       | +0.111%         |
| Buy and hold | 1495    | 46.9%       | +0.220%         |

Verdict: timing UNDERPERFORMS buy-and-hold by 0.109% — do not trade on this
```

**This is the project's real current state, not demo data.** A 53% win rate looks
acceptable in isolation, but three checks converge on the same conclusion: z=0.88
falls short of significance; strategy expectancy is half of buy-and-hold; and the
strong-signal bucket (|score|≥40) wins 53.2% versus 53.5% for the medium bucket —
essentially no discrimination. Silver is worse: the strong bucket wins 46.8% against
55.6% for medium.

Keeping this negative result instead of tuning until it looks good is the point —
backtesting earns its keep by falsifying.

### Weight & Holding-Period Tuning Verification (done — verdict: do not tune)

Verified in the only defensible order — factor IC test → weight optimisation on
surviving factors → out-of-sample validation (`python scripts/tune_verify.py`,
full write-up in [docs/因子调优验证报告.md](docs/因子调优验证报告.md)):

1. **No factor clears the bar.** All six gold factors have |IC| < 0.09; most silver
   factors are negative. |IC| < 0.03 is conventionally treated as noise.
2. **Weights are not the lever.** Equal-weight and current-weight differ by 0.002 in
   IC. The in-sample grid optimum (rsi alone) flips negative out-of-sample
   (IS +0.124 → OOS -0.079) — textbook overfitting.
3. **The OOS improvement is beta, not alpha.** Gold rose +82% and silver +141% over
   the OOS window; any long-biased indicator correlates with forward returns there.
4. **Rolling windows say the opposite.** Rolling 1-year IC (20d horizon) averages
   **-0.269** for gold and **-0.246** for silver, negative in 7-8 of 9 windows. The
   +0.21 full-period OOS figure is Simpson's paradox: cross-window drift manufactures
   spurious positive correlation. The within-window negative sign is the real one.

Therefore: **default weights unchanged, holding period not extended, no silver
inversion.** All six factors are price-derived and highly collinear on precious
metals; the way forward is orthogonal information (real rates, ETF holdings, COMEX
inventories, DXY), not re-mixing the same price series.

**The signal engine is repositioned accordingly: it is a reproducible, auditable,
lookahead-free discipline framework — the score itself is not currently an entry
criterion.**

### Report Dimensions

| Dimension | Purpose |
|-----------|---------|
| Win rate / profit factor / expectancy | Baseline performance |
| **Buy-and-hold benchmark** | Separates alpha from beta — a permabull scores 55% in a bull market |
| **Binomial significance test** | Reports z and p above 30 samples; explicitly flags insufficient samples otherwise |
| **Win rate stratified by signal strength** | If strong signals don't beat weak ones, the score is repackaged noise |
| **Holding-period decay curve** | Win rate at 1/3/5/10/20 days — momentum or trend? |
| Max drawdown | Depth of consecutive misses across the equal-weighted signal series (not a real account curve) |

### Configuration

```yaml
backtest:
  horizon_days: 5      # holding period in calendar days
  threshold_pct: 0.5   # minimum move to count as directional; below this is "flat"

backfill:
  warmup_bars: 120     # warmup bars so MA60/MACD are stable
  # step_bars: 5       # sampling stride; defaults to horizon_days when omitted
```

### Daily Automation

```bash
# cron: collect on weekdays at 06:30, run a backtest on Mondays
30 6 * * 1-5 /path/to/metal_trend_analysis/scripts/daily_signal_cron.sh
```

On macOS prefer `scripts/com.metaltrend.daily.plist` (launchd) over cron: launchd
re-runs jobs missed while the machine was asleep, whereas cron simply skips them —
and a skipped day is a permanently missing sample.


## 🧪 Testing

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run the full suite
pytest -v

# With coverage
pytest --cov=src --cov-report=term-missing

# Check for duplicate definitions (also runs in CI)
python scripts/check_duplicates.py
```

## 🐳 Docker Deployment

MetalTrend AI provides Docker deployment with one-click startup and scheduled execution.

### Quick Start

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Edit .env file with your API keys
vim .env

# 3. Start container
docker-compose up -d

# 4. View logs
docker-compose logs -f
```

> Tip: The container reads `config/config.yaml` by default. Make sure it exists and is configured.

### One-shot Run (no schedule)

```bash
# Run once and exit
docker-compose run --rm -e CRON_SCHEDULE= metal-trend-analysis

# Run a specific instrument and timeframe
docker-compose run --rm -e CRON_SCHEDULE= -e INSTRUMENT=gold -e TIMEFRAME=1h metal-trend-analysis
```

### Scheduled Execution

Configure scheduled analysis via `CRON_SCHEDULE` environment variable:

```bash
# Run daily at 9 AM
docker-compose run -e CRON_SCHEDULE="0 9 * * *" metal-trend-analysis

# Run every hour
docker-compose run -e CRON_SCHEDULE="0 * * * *" metal-trend-analysis

# Custom timezone (optional)
docker-compose run -e CRON_SCHEDULE="0 9 * * *" -e TZ=Asia/Shanghai metal-trend-analysis
```

### Common Operations

```bash
# Stop and remove containers
docker-compose down

# Rebuild images
docker-compose up -d --build

# Tail cron log (inside container)
docker-compose exec metal-trend-analysis tail -f /app/output/logs/cron.log
```

For detailed instructions, see [SETUP_EN.md](SETUP_EN.md#docker-deployment-recommended)

## 📰 News Sentiment Analysis Feature

MetalTrend AI now integrates powerful news sentiment analysis capabilities, fetching relevant news from multiple authoritative sources and automatically analyzing market sentiment.

### 🏢 Supported News Sources

The system currently includes the following verified and available news sources:

#### English News Sources
- **Bloomberg Markets** - World's leading business and financial market information provider
- **CNBC Market News** - Authoritative US business news source

#### Chinese News Sources  
- **Phoenix Finance** - Well-known Chinese financial media
- **Wallstreetcn** - Major financial news platform
- **CLS Telegraph** - Financial flashes and market telegraphs
- **The Paper** - Comprehensive news coverage

> Note: Some sources use **HTML parsing + Jina AI text proxy** to support sites without public RSS feeds.

### 🔧 How It Works

1. **News Fetching**: System periodically fetches latest news from configured RSS / HTML / API sources
2. **Keyword Filtering**: Filters relevant news based on keywords in `config/keywords.txt`
3. **Sentiment Analysis**: Uses built-in sentiment lexicon to analyze positive/negative words in each article
4. **Comprehensive Analysis**: Combines with technical analysis for holistic market insights

### ⚙️ Configuration Guide

In `config/config.yaml`, you can configure the following news-related options:

```yaml
news:
  enabled: true  # Enable news fetching
  max_articles: 10  # Maximum articles per source
  cache_duration: 300  # Cache duration (seconds, 5 minutes)
  fetch:
    timeout: 15
    delay: 2  # Request delay between different sources (seconds)
    max_retries: 3
  sources:
    # Enable or disable different news sources as needed
    - name: "Bloomberg Markets"
      type: "rss"
      url: "https://feeds.bloomberg.com/markets/news.rss"
      enabled: true
    - name: "WallstreetCN"
      type: "html"
      url: "https://r.jina.ai/http://wallstreetcn.com/"
      parser: "markdown_links"
      link_contains:
        - "wallstreetcn.com/articles"
        - "wallstreetcn.com/livenews"
      enabled: true
    # ... other news source configurations
```

### 📊 Report Integration

News sentiment analysis results are integrated into the final Markdown reports:
- **News Sentiment Statistics**: Shows overall market sentiment trend
- **Key Theme Identification**: Extracts high-frequency positive/negative words
- **Representative Articles**: Displays most influential news articles
- **LLM Deep Analysis**: Provides professional market insights combined with news content

### ✅ News Source Test

Use the test script to validate news source availability:

```bash
python scripts/check_news_sources.py
```

It reads `config/config.yaml` by default, falling back to `config/config.yaml.example` if missing.

## 📁 Project Structure

```
metal_trend_analysis/
├── config/                # Configuration files
│   ├── config.yaml        # Main configuration file
│   └── keywords.txt       # News keywords
├── data/                  # Raw data and cache
├── docker/                # Docker scripts
├── docs/                  # Internal documentation
│   └── internal/
├── images/                # Images for README and reports
├── output/                # Program output
│   ├── logs/              # Log files
│   └── reports/           # Generated Markdown reports
├── scripts/               # Helper scripts
├── src/                   # Core source code
│   ├── main.py            # 🚀 Main entry point
│   ├── analyzers/         # 📊 Analysis modules (indicators, patterns, news sentiment)
│   ├── data_fetchers/     # 📡 Data fetching modules (Sina / Stooq / Yahoo, news fetching)
│   ├── llm/               # 🤖 LLM analysis modules
│   ├── notification/      # 📢 Notification modules (Feishu/DingTalk/Slack/Telegram/Email)
│   ├── reporting/         # 📄 Report generation modules
│   └── utils/             # 🛠️ Utility classes (config loading, logging)
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile             # Docker image build
├── .gitignore
├── LICENSE
├── README.md              # Chinese README
├── README_EN.md           # English README
└── requirements.txt       # Python dependencies
```

## 🏗️ System Architecture

MetalTrend AI adopts a modular architecture design with clear responsibilities for each component, making it easy to extend and maintain.

### Core Module Descriptions

1. **Data Fetching Module** (`data_fetchers/`)
  - Uses Sina Finance (primary) with Stooq / Yahoo Finance failover for daily prices
   - Supports multiple timeframe K-line data
   - Built-in data caching mechanism to reduce API calls

2. **Analysis Engine** (`analyzers/`)
   - Technical indicator calculations (MA, MACD, RSI, Bollinger Bands, etc.)
   - Candlestick pattern recognition (Doji, Hammer, Engulfing, etc.)
   - News sentiment analysis (market sentiment quantification)
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
  - Feishu / DingTalk / Slack / Telegram / Email notifications
  - Auto-enabled via environment variables
  - Push failure retry mechanism

---

## 🗺️ Roadmap

### ✅ Completed - v1.0
- [x] Stooq free data fetching
- [x] Technical indicator calculations (MA, MACD, RSI, Bollinger Bands)
- [x] Candlestick pattern recognition (10+ classic patterns)
- [x] LLM analysis integration (GPT-4 support)
- [x] Automatic report generation (Markdown format)
- [x] Feishu notification functionality
- [x] News fetching and sentiment analysis (integrated verified sources: Bloomberg, CNBC, Phoenix Finance, etc.)

### ✅ Completed - v1.1
- [x] Docker one-click deployment (with cron support, default timezone Asia/Shanghai)

### 📅 Planned - v1.2
- [ ] Configuration wizard
- [ ] Error handling optimization
- [ ] Unit test coverage
- [ ] CI/CD pipeline
- [ ] Web interface (Streamlit)
- [ ] More technical indicators (KDJ, OBV, etc.)
- [ ] Custom trading strategy support
- [ ] Historical data backtesting

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
| **LLM/AI** | OpenAI-compatible APIs (OpenAI / DeepSeek / Qwen) |
| **Technical Analysis** | In-house indicators (Pandas / NumPy) |
| **Visualization** | Matplotlib, Plotly (optional) |
| **API** | Sina Finance / Stooq / Yahoo Finance (free), Feishu / DingTalk / Slack / Telegram / Email |

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

- [Internal Documentation](docs/internal/)

## 🌟 Community & Support

- **GitHub Issues**: Report bugs or suggest new features

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
