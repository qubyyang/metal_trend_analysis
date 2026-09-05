#!/usr/bin/env bash
#
# 每日信号采集与周期性回测
#
# 用途：由 cron / launchd 定时调用，完成两件事
#   1. 运行一次完整分析，把当日信号写入 signals.jsonl
#   2. 每周一额外跑一次回测，输出滚动统计报告
#
# 安装（cron，每个交易日 06:30 运行）：
#   crontab -e
#   30 6 * * 1-5 /path/to/metal_trend_analysis/scripts/daily_signal_cron.sh
#
# 安装（macOS launchd，休眠错过后会补跑，比 cron 更可靠）：
#   见 scripts/com.metaltrend.daily.plist
#
# 注意：脚本用绝对路径解析项目根目录，不依赖调用时的工作目录——
# cron 的默认工作目录是 $HOME，用相对路径必然失败。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Python 解释器：优先用项目 venv，其次环境变量，最后回落到 python3
if [ -x "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python"
elif [ -n "${METALTREND_PYTHON:-}" ]; then
    PYTHON="$METALTREND_PYTHON"
else
    PYTHON="$(command -v python3)"
fi

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cron_$(date +%Y%m).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

log "=== 每日信号采集开始 ==="
log "Python: $PYTHON"

# 采集当日信号。--no-chart 省去绘图开销，定时任务不需要图表。
if "$PYTHON" -m src.main --no-chart >> "$LOG_FILE" 2>&1; then
    log "信号采集完成"
else
    log "信号采集失败，退出码 $?"
    exit 1
fi

# 每周一跑一次回测。每天跑没有意义——
# 5 日持有期下，一天只新增 1~2 条已到期样本，统计结论不会变化。
if [ "$(date +%u)" = "1" ]; then
    log "周一，执行滚动回测"
    if "$PYTHON" -m src.main --backtest >> "$LOG_FILE" 2>&1; then
        log "回测完成，报告位于 output/reports/"
    else
        log "回测失败，退出码 $?"
    fi
fi

log "=== 结束 ==="
