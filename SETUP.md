# 安装和配置指南

## ✅ 适用环境

- Python 3.10+（推荐使用 3.10/3.11）
- macOS / Linux / Windows

## 🚀 快速开始（5分钟）

### 步骤 1: 克隆项目

```bash
cd /path/to/your/workspace
# git clone <repository_url>
cd metal_trend_analysis
```

### 步骤 2: 一键初始化（可选）

```bash
./start.sh
```

该脚本会自动：
- 检查 Python 版本
- 创建虚拟环境
- 安装依赖
- 检查配置文件

## 🧰 手动配置（推荐）

### 1. 环境准备

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 获取 API 密钥

#### iTick API（必需）

1. 访问 https://itick.org 注册账号
2. 进入控制台获取 API Token
3. 免费套餐：5次/分钟调用

#### LLM API（必需）

可选择：OpenAI / DeepSeek / 通义千问 / 其他兼容 OpenAI 接口的服务。

### 3. 配置系统

#### 方法 A: 使用环境变量（推荐）

```bash
cp .env.example .env
vim .env
```

填写配置：

```env
ITICK_API_TOKEN=your_itick_token_here
LLM_API_KEY=your_llm_api_key_here
LLM_BASE_URL=https://api.deepseek.com/v1  # 可选
LLM_MODEL_NAME=gpt-4o  # 或 deepseek-chat

# 可选：飞书推送（留空则不启用）
FEISHU_WEBHOOK_URL=
```

#### 方法 B: 直接编辑配置文件

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

### 4. 验证配置

```bash
source venv/bin/activate
python src/main.py --debug
```

## ⚙️ 详细配置说明

### iTick API 配置

`config/itick_config.yaml`：

```yaml
base_url: "https://api.itick.org/forex"
token: ""  # 你的 API Token
timeout: 30
retry: 3
retry_delay: 2
```

### LLM 配置

`config/config.yaml`：

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

### 飞书推送配置（可选）

1. 飞书群 → 群设置 → 群机器人 → 添加「自定义机器人」
2. 复制 Webhook URL
3. 写入 `.env`：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
```

若 `FEISHU_WEBHOOK_URL` 为空，则不会发送推送。
  channels:
    feishu:
      enabled: true
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

#### 推送效果

- 📊 每日汇总报告（黄金白银概览 + 黄金白银比）
- 📈 单品种详细报告（行情、技术指标、K线形态、AI分析）
- 🔔 支持卡片消息格式，移动端阅读友好

### 新闻源配置

在 `config/news_sources.yaml` 中可以：
- 添加/删除新闻源
- 启用/禁用特定新闻源
- 调整请求参数

### 技术指标配置

在 `config/config.yaml` 中可以调整技术指标参数：

```yaml
indicators:
  ma:
    periods: [5, 10, 20, 60]  # MA 周期
  macd:
    fast: 12
    slow: 26
    signal: 9
  rsi:
    period: 14
    overbought: 70  # 超买阈值
    oversold: 30  # 超卖阈值
  bollinger:
    period: 20
    std_dev: 2  # 标准差倍数
```

## 常见问题

### Q1: pip 安装失败

**问题**: `ta-lib` 安装失败

**解决方案**:
```bash
# Mac
brew install ta-lib

# Ubuntu/Debian
sudo apt-get install ta-lib

# Windows
# 从 https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib 下载预编译包
# 然后安装: pip install TA_Lib-0.4.xx-cpxx-cpxx-win_amd64.whl
```

### Q2: iTick API 返回 401

**问题**: API Token 无效

**解决方案**:
1. 检查 `.env` 文件中的 token 是否正确
2. 访问 iTick 控制台重新生成 token
3. 确保没有多余的空格或引号

### Q3: LLM API 超时

**问题**: LLM 请求超时

**解决方案**:
1. 增加 `timeout` 参数（如 120 秒）
2. 使用更快的模型（如 gpt-3.5-turbo）
3. 检查网络连接

### Q4: 虚拟环境激活失败

**问题**: 无法激活虚拟环境

**解决方案**:
```bash
# 删除旧的虚拟环境
rm -rf venv

# 重新创建
python3 -m venv venv

# 激活
source venv/bin/activate
```

### Q5: 新闻抓取失败

**问题**: 无法获取新闻

**解决方案**:
1. 检查网络连接
2. 增加 `config.yaml` 中的 `timeout` 值
3. 暂时禁用有问题的新闻源

## 运行示例

### 基本运行

```bash
# 分析所有品种（黄金和白银）
python src/main.py

# 只分析黄金
python src/main.py --instrument gold

# 只分析白银
python src/main.py --instrument silver

# 指定时间周期
python src/main.py --timeframe 4h

# 调试模式
python src/main.py --debug
```

### 使用启动脚本

```bash
# 基本运行
./start.sh

# 传递参数
./start.sh --instrument gold --timeframe 4h
```

## 查看报告

生成的报告保存在 `output/reports/` 目录：

```bash
# 查看最新的报告
ls -lt output/reports/ | head -5

# 查看报告内容
cat output/reports/report_XAUUSD_20260127_101523.md
```

## 下一步

配置完成后，你可以：

1. **定期分析**: 使用 cron 或定时任务定期运行
2. **自定义配置**: 根据需求调整技术指标参数
3. **扩展功能**: 添加新的技术指标或新闻源
4. **数据可视化**: 集成图表库生成可视化报告

## 技术支持

如有问题，请查看：
- README.md - 项目说明
- output/logs/app.log - 运行日志
- 使用 `--debug` 参数运行查看详细信息

---

**祝使用愉快！**
