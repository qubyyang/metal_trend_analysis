# Installation and Configuration Guide

## ✅ Prerequisites

- Python 3.10+ (recommended: 3.10/3.11)
- macOS / Linux / Windows

## 🚀 Quick Start (5 minutes)

### Step 1: Clone the Project

```bash
cd /path/to/your/workspace
# git clone <repository_url>
cd metal_trend_analysis
```

### Step 2: One-Click Setup (Optional)

```bash
./start.sh
```

This script will automatically:
- Check Python version
- Create virtual environment
- Install dependencies
- Validate configuration files

## 🧰 Manual Setup (Recommended)

### 1. Environment Setup

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Get API Keys

#### iTick API (Required)

1. Visit https://itick.org and register
2. Go to the console and get your API Token
3. Free tier: 5 calls/minute

#### LLM API (Required)

Use OpenAI / DeepSeek / Qwen, or any OpenAI-compatible service.

### 3. Configure the System

#### Method A: Environment Variables (Recommended)

```bash
cp .env.example .env
vim .env
```

Fill in your credentials:

```env
ITICK_API_TOKEN=your_itick_token_here
LLM_API_KEY=your_llm_api_key_here
LLM_BASE_URL=https://api.deepseek.com/v1  # Optional
LLM_MODEL_NAME=gpt-4o  # Or deepseek-chat

# Optional: Feishu notifications (leave empty to disable)
FEISHU_WEBHOOK_URL=
```

#### Method B: Direct Config File Edit

```bash
vim config/config.yaml
```

```yaml
api:
  itick:
    token: "your_itick_token_here"

llm:
  api_key: "your_llm_api_key_here"
  base_url: "https://api.deepseek.com/v1"
  model: "gpt-4o"
```

### 4. Verify Configuration

```bash
source venv/bin/activate
python src/main.py --debug
```

## ⚙️ Detailed Configuration

### iTick API

`config/itick_config.yaml`:

```yaml
base_url: "https://api.itick.org/forex"
token: ""  # Your API Token
timeout: 30
retry: 3
retry_delay: 2
```

### LLM

`config/config.yaml`:

```yaml
llm:
  provider: "openai"
  api_key: "${LLM_API_KEY}"
  base_url: "${LLM_BASE_URL}"
  model: "${LLM_MODEL_NAME}"
  temperature: 0.7
  max_tokens: 2000
  timeout: 60
```

**Supported Models**:
- OpenAI: gpt-4o, gpt-4-turbo, gpt-3.5-turbo
- DeepSeek: deepseek-chat, deepseek-coder
- Qwen: qwen-turbo, qwen-plus, qwen-max

### Feishu Notifications (Optional)

1. Feishu group → Group settings → Bots → Add custom bot
2. Copy the Webhook URL
3. Add to `.env`:

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
```

If `FEISHU_WEBHOOK_URL` is empty, no notifications will be sent.

### Q1: pip install fails

**Problem**: `ta-lib` installation fails

**Solution**:
```bash
# Mac
brew install ta-lib

# Ubuntu/Debian
sudo apt-get install ta-lib

# Windows
# Download pre-compiled package from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
# Then install: pip install TA_Lib-0.4.xx-cpxx-cpxx-win_amd64.whl
```

### Q2: iTick API returns 401

**Problem**: API Token invalid

**Solution**:
1. Check if token in `.env` file is correct
2. Regenerate token from iTick console
3. Ensure no extra spaces or quotes

### Q3: LLM API timeout

**Problem**: LLM request timeout

**Solution**:
1. Increase `timeout` parameter (e.g., 120 seconds)
2. Use faster model (e.g., gpt-3.5-turbo)
3. Check network connection

### Q4: Virtual environment activation fails

**Problem**: Cannot activate virtual environment

**Solution**:
```bash
# Delete old virtual environment
rm -rf venv

# Recreate
python3 -m venv venv

# Activate
source venv/bin/activate
```

### Q5: News scraping fails

**Problem**: Cannot fetch news

**Solution**:
1. Check network connection
2. Increase `timeout` value in `config.yaml`
3. Temporarily disable problematic news sources

## Running Examples

### Basic Run

```bash
# Analyze all instruments (gold and silver)
python src/main.py

# Analyze gold only
python src/main.py --instrument gold

# Analyze silver only
python src/main.py --instrument silver

# Specify timeframe
python src/main.py --timeframe 4h

# Debug mode
python src/main.py --debug
```

### Using Startup Script

```bash
# Basic run
./start.sh

# Pass parameters
./start.sh --instrument gold --timeframe 4h
```

## Viewing Reports

Generated reports are saved in `output/reports/`:

```bash
# View latest reports
ls -lt output/reports/ | head -5

# View report content
cat output/reports/report_XAUUSD_20260127_101523.md
```

## Next Steps

After configuration, you can:

1. **Regular Analysis**: Use cron or scheduled tasks for periodic runs
2. **Custom Configuration**: Adjust technical indicator parameters as needed
3. **Extend Functionality**: Add new technical indicators or news sources
4. **Customize LLM Prompts**: Modify prompts in `src/llm/analyzer.py`
5. **Data Visualization**: Integrate chart libraries for visual reports

## Technical Support

For issues, please check:
- README.md - Project documentation
- README_EN.md - English documentation
- output/logs/app.log - Runtime logs
- Use `--debug` parameter for detailed information

---

**Happy Using!**
