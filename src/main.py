"""
Metal Trend Analysis Tool - Main Program
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import ConfigLoader
from src.utils.logger import setup_logger, get_logger
from src.data_fetchers.market_data import MarketDataClient
from src.data_fetchers.news_fetcher import NewsFetcher
from src.analyzers.technical import TechnicalAnalyzer
from src.analyzers.patterns import PatternRecognizer
from src.analyzers.news_sentiment import NewsSentimentAnalyzer
from src.analyzers.signal_tracker import SignalTracker
from src.analyzers.cross_asset import CrossAssetAnalyzer
from src.llm.analyzer import LLMAnalyzer
from src.reporting.generator import ReportGenerator
from src.reporting.chart import ChartGenerator
from src.notification.feishu import FeishuNotifier
from src.notification.dingtalk import DingTalkNotifier
from src.notification.slack import SlackNotifier
from src.notification.telegram import TelegramNotifier
from src.notification.email import EmailNotifier


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Metal Trend Analysis Tool')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Configuration file path')
    parser.add_argument('--instrument', type=str, default='all',
                        choices=['all', 'gold', 'silver', 'XAUUSD', 'XAGUSD'],
                        help='Instrument to analyze')
    parser.add_argument('--timeframe', type=str, default='1d',
                        help='Timeframe (1d/1w/1m - Stooq daily data)')
    parser.add_argument('--debug', action='store_true',
                        help='Debug mode')
    parser.add_argument('--no-chart', action='store_true',
                        help='Disable chart generation')
    parser.add_argument('--backtest', action='store_true',
                        help='Only evaluate historical signal accuracy, skip analysis')
    parser.add_argument('--no-cross-asset', action='store_true',
                        help='Disable cross-asset ratio/correlation analysis')
    return parser.parse_args()


def initialize_analyzers(config: Dict[str, Any], logger) -> Tuple[Dict[str, Any], bool]:
    """
    Initialize all analyzer modules.

    Returns:
        Tuple of (analyzers_dict, success)
    """
    analyzers = {}

    try:
        # Market data client (multi-source with automatic failover)
        market_config = config.get('api', {}).get('stooq', {}).copy()
        market_config.update(config.get('market_data', {}))
        analyzers['market_client'] = MarketDataClient(market_config)
        logger.info("Market data client initialized successfully")

        # Technical analyzer
        indicators_config = config.get('indicators', {})
        analyzers['technical_analyzer'] = TechnicalAnalyzer(indicators_config)
        logger.info("Technical analyzer initialized successfully")

        # Pattern recognizer
        analyzers['pattern_recognizer'] = PatternRecognizer()
        logger.info("Pattern recognizer initialized successfully")

        # LLM analyzer (optional: technical analysis remains usable without it)
        llm_config = config.get('llm', {})
        try:
            analyzers['llm_analyzer'] = LLMAnalyzer(llm_config)
            logger.info("LLM analyzer initialized successfully")
        except Exception as e:
            analyzers['llm_analyzer'] = None
            logger.warning(
                f"LLM analyzer unavailable, falling back to technical-only analysis: {e}"
            )

        # Report generator
        reports_config = config.get('reports', {})
        analyzers['report_generator'] = ReportGenerator(reports_config)
        logger.info("Report generator initialized successfully")

        # Chart generator (optional, degrades gracefully without matplotlib)
        analyzers['chart_generator'] = ChartGenerator(reports_config)
        if analyzers['chart_generator'].available:
            logger.info("Chart generator initialized successfully")
        else:
            logger.warning("matplotlib not installed, charts disabled")

        # Signal tracker for accuracy backtesting
        analyzers['signal_tracker'] = SignalTracker(config.get('backtest', {}))
        logger.info("Signal tracker initialized successfully")

        # Cross-asset analyzer (optional enhancement)
        analyzers['cross_asset'] = CrossAssetAnalyzer(config.get('cross_asset', {}))
        logger.info("Cross-asset analyzer initialized successfully")

        return analyzers, True

    except Exception as e:
        logger.error(f"Failed to initialize analyzers: {e}")
        return {}, False


def initialize_news_modules(config: Dict[str, Any], logger) -> Tuple[Optional[Any], Optional[Any], List[Dict[str, Any]]]:
    """
    Initialize news fetcher and sentiment analyzer.

    Returns:
        Tuple of (news_fetcher, sentiment_analyzer, news_articles)
    """
    news_config = config.get('news', {})

    if not news_config.get('enabled', False):
        logger.info("News fetching is disabled in configuration")
        return None, None, []

    try:
        # Load keywords
        keywords_file = Path('config/keywords.txt')
        keywords = []
        if keywords_file.exists():
            with open(keywords_file, 'r', encoding='utf-8') as f:
                keywords = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            logger.info(f"Loaded {len(keywords)} keywords from {keywords_file}")
        else:
            logger.warning(f"Keywords file not found: {keywords_file}")

        # Check if news sources are configured
        news_sources = news_config.get('sources', [])
        if not news_sources:
            logger.warning("No news sources configured in config.yaml")

        # Initialize news fetcher
        news_fetcher = NewsFetcher(config=news_config, keywords=keywords)
        logger.info(f"News fetcher initialized with {len(news_sources)} sources")

        # Initialize sentiment analyzer
        sentiment_analyzer = NewsSentimentAnalyzer()
        logger.info("News sentiment analyzer initialized successfully")

        # Fetch news
        logger.info("Fetching news articles...")
        news_articles = news_fetcher.fetch_all_news(use_cache=True)
        logger.info(f"Fetched {len(news_articles)} news articles")

        return news_fetcher, sentiment_analyzer, news_articles

    except Exception as e:
        logger.error(f"Failed to initialize news modules: {str(e)}")
        return None, None, []


def _safe_init_notifier(notifiers: Dict[str, Any], name: str, factory, logger) -> None:
    """
    Safely construct a notifier; misconfiguration disables only that channel.

    Notification is an auxiliary capability — an invalid webhook or credential
    must never abort the analysis pipeline.
    """
    try:
        notifiers[name] = factory()
        logger.info(f"{name} notifier initialized successfully")
    except Exception as e:
        logger.warning(f"{name} notifier misconfigured, channel disabled: {e}")


def initialize_notifiers(config: Dict[str, Any], logger) -> Dict[str, Any]:
    """
    Initialize all notification services.

    Returns:
        Dictionary of available notifiers
    """
    notification_config = config.get('notification', {}).get('channels', {})
    notifiers = {}

    # Feishu notifier
    feishu_config = notification_config.get('feishu', {})
    feishu_webhook = feishu_config.get('webhook_url', '')
    if feishu_webhook:
        _safe_init_notifier(notifiers, 'Feishu', lambda: FeishuNotifier(
            webhook_url=feishu_webhook,
            timeout=feishu_config.get('timeout', 30)
        ), logger)
    else:
        logger.info("Feishu webhook URL not configured, Feishu notifications disabled")

    # DingTalk notifier
    dingtalk_config = notification_config.get('dingtalk', {})
    dingtalk_webhook = dingtalk_config.get('webhook_url', '')
    if dingtalk_webhook:
        _safe_init_notifier(notifiers, 'DingTalk', lambda: DingTalkNotifier(
            webhook_url=dingtalk_webhook,
            timeout=dingtalk_config.get('timeout', 30)
        ), logger)
    else:
        logger.info("DingTalk webhook URL not configured, DingTalk notifications disabled")

    # Slack notifier
    slack_config = notification_config.get('slack', {})
    slack_webhook = slack_config.get('webhook_url', '')
    if slack_webhook:
        _safe_init_notifier(notifiers, 'Slack', lambda: SlackNotifier(
            webhook_url=slack_webhook,
            timeout=slack_config.get('timeout', 30)
        ), logger)
    else:
        logger.info("Slack webhook URL not configured, Slack notifications disabled")

    # Telegram notifier
    telegram_config = notification_config.get('telegram', {})
    telegram_bot_token = telegram_config.get('bot_token', '')
    telegram_chat_id = telegram_config.get('chat_id', '')
    if telegram_bot_token and telegram_chat_id:
        _safe_init_notifier(notifiers, 'Telegram', lambda: TelegramNotifier(
            bot_token=telegram_bot_token,
            chat_id=telegram_chat_id,
            timeout=telegram_config.get('timeout', 30)
        ), logger)
    else:
        logger.info("Telegram bot token or chat ID not configured, Telegram notifications disabled")

    # Email notifier
    email_config = notification_config.get('email', {})
    email_from = email_config.get('from', '')
    email_password = email_config.get('password', '')
    email_to = email_config.get('to', '')
    if email_from and email_password and email_to:
        _safe_init_notifier(notifiers, 'Email', lambda: EmailNotifier(
            from_email=email_from,
            password=email_password,
            to_email=email_to,
            smtp_server=email_config.get('smtp_server'),
            smtp_port=email_config.get('smtp_port'),
            timeout=email_config.get('timeout', 30)
        ), logger)
    else:
        logger.info("Email configuration not complete, Email notifications disabled")

    return notifiers


def get_instruments_to_analyze(args: argparse.Namespace, config: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Determine which instruments to analyze based on arguments and configuration.

    Returns:
        List of (instrument_name, instrument_config) tuples
    """
    instruments_config = config.get('instruments', {})
    instruments_to_analyze = []

    if args.instrument == 'all':
        instruments_to_analyze = [
            ('gold', instruments_config.get('gold', {})),
            ('silver', instruments_config.get('silver', {}))
        ]
    else:
        # Determine instrument based on parameter
        if args.instrument in ['gold', 'XAUUSD']:
            instruments_to_analyze.append(('gold', instruments_config.get('gold', {})))
        elif args.instrument in ['silver', 'XAGUSD']:
            instruments_to_analyze.append(('silver', instruments_config.get('silver', {})))

    return instruments_to_analyze


def analyze_instrument(
    instrument_name: str,
    instrument_config: Dict[str, Any],
    analyzers: Dict[str, Any],
    sentiment_analyzer: Optional[Any],
    news_articles: List[Dict[str, Any]],
    timeframe: str,
    logger,
    debug: bool = False,
    enable_chart: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Analyze a single instrument.

    Returns:
        Analysis results dictionary or None if failed
    """
    if not instrument_config.get('enabled', True):
        logger.info(f"{instrument_name} is not enabled, skipping")
        return None

    symbol = instrument_config.get('symbol')
    symbol_name = instrument_config.get('name')
    region = instrument_config.get('region', 'GB')

    logger.info(f"")
    logger.info(f"Starting analysis for {symbol_name} ({symbol})...")
    logger.info("-" * 60)

    try:
        market_client = analyzers['market_client']
        technical_analyzer = analyzers['technical_analyzer']
        pattern_recognizer = analyzers['pattern_recognizer']
        llm_analyzer = analyzers['llm_analyzer']
        report_generator = analyzers['report_generator']
        chart_generator = analyzers.get('chart_generator')
        signal_tracker = analyzers.get('signal_tracker')

        # Get real-time quote
        logger.info(f"Fetching real-time quote for {symbol}...")
        quote_data = market_client.get_quote(symbol, region)
        if quote_data:
            quote_data['symbol'] = symbol

        if not quote_data:
            logger.error(f"Failed to fetch quote for {symbol}")
            return None

        logger.info(f"Current price: ${quote_data.get('price')} (source: {quote_data.get('source')})")
        logger.info(f"Change: {quote_data.get('change')} ({quote_data.get('change_percent')}%)")

        # Get K-line data
        logger.info(f"Fetching K-line data for {symbol}...")
        kline_data = market_client.get_kline(symbol, timeframe)

        if kline_data.empty:
            logger.error(f"Failed to fetch K-line data for {symbol}")
            return None

        logger.info(f"Fetched {len(kline_data)} K-line records")

        # Save raw data
        market_client.save_raw_data(kline_data, symbol, timeframe)

        # Calculate technical indicators
        logger.info("Calculating technical indicators...")
        indicator_data = technical_analyzer.calculate_all_indicators(kline_data)

        # Trend analysis
        trend_analysis = technical_analyzer.get_trend_analysis(indicator_data)

        # Support and resistance levels
        support_levels, resistance_levels = technical_analyzer.identify_support_resistance(kline_data)

        technical_result = {
            **trend_analysis,
            'support_levels': support_levels,
            'resistance_levels': resistance_levels
        }

        logger.info(f"Technical trend: {trend_analysis.get('trend', 'N/A')}")
        logger.info(f"Support levels: {[f'${s:.2f}' for s in support_levels[:2]]}")
        logger.info(f"Resistance levels: {[f'${r:.2f}' for r in resistance_levels[:2]]}")

        # Identify K-line patterns
        logger.info("Identifying K-line patterns...")
        patterns = pattern_recognizer.detect_patterns(kline_data)
        pattern_summary = pattern_recognizer.get_pattern_summary(patterns)

        logger.info("K-line patterns:")
        if pattern_summary:
            for line in pattern_summary.split('\n'):
                if line.strip():
                    logger.info(f"  {line}")

        technical_result['patterns'] = patterns

        # Generate technical chart
        chart_path = None
        if enable_chart and chart_generator and chart_generator.available:
            logger.info("Generating technical chart...")
            chart_path = chart_generator.generate(
                indicator_data,
                symbol,
                symbol_name,
                timeframe,
                support_levels=support_levels,
                resistance_levels=resistance_levels
            )
            if chart_path:
                logger.info(f"Chart saved to: {chart_path}")

        # LLM comprehensive analysis (skipped when LLM is unavailable)
        if llm_analyzer is None:
            logger.warning("LLM analyzer unavailable, skipping AI commentary")
            llm_result = {'error': 'LLM analyzer not configured', 'analysis': {}}
        else:
            logger.info("Performing LLM comprehensive analysis...")
            llm_result = llm_analyzer.analyze_market(
                symbol,
                quote_data,
                technical_result,
                news_articles
            )

        if llm_result.get('error'):
            logger.warning(f"LLM analysis failed: {llm_result['error']}")
        else:
            logger.info("LLM analysis successful")
            analysis = llm_result.get('analysis', {})
            if analysis:
                logger.info(f"Trend direction: {analysis.get('trend', 'N/A')}")
                logger.info(f"Trading suggestion: {analysis.get('suggestion', 'N/A')}")
                logger.info(f"Risk level: {analysis.get('risk_level', 'N/A')}")

        # Generate report
        logger.info("Generating analysis report...")

        # Add news sentiment to technical result
        if sentiment_analyzer and news_articles:
            sentiment_result = sentiment_analyzer.analyze_articles_sentiment(news_articles)
            technical_result['news_sentiment'] = sentiment_result
            logger.info(f"News sentiment: {sentiment_result.get('overall_sentiment', 'N/A')}")

        report_content = report_generator.generate_markdown_report(
            symbol,
            symbol_name,
            quote_data,
            technical_result,
            news_articles,
            llm_result
        )

        report_path = report_generator.save_report(report_content, symbol, timeframe)
        logger.info(f"Report saved to: {report_path}")

        # Record signal for future accuracy evaluation
        if signal_tracker:
            try:
                signal_tracker.record(
                    symbol, quote_data, technical_result, llm_result, timeframe
                )
            except Exception as e:
                logger.warning(f"Failed to record signal for {symbol}: {e}")

        logger.info(f"{symbol_name} analysis completed")
        logger.info("-" * 60)

        return {
            'symbol': symbol,
            'quote': quote_data,
            'technical': technical_result,
            'llm': llm_result,
            'report_path': report_path,
            'chart_path': chart_path,
            'kline_data': kline_data
        }

    except Exception as e:
        logger.error(f"Error analyzing {symbol_name}: {str(e)}")
        if debug:
            import traceback
            logger.error(traceback.format_exc())
        return None


def run_cross_asset_analysis(
    analyzers: Dict[str, Any],
    analysis_results: Dict[str, Any],
    config: Dict[str, Any],
    logger,
) -> Optional[Dict[str, Any]]:
    """Run cross-asset ratio and correlation analysis.

    主分析已经取过金银日线，这里只需**增量**拉取辅助品种
    （铂金、铜、原油、美元指数）。辅助品种纯属增强项：
    任何一个拉取失败都只是少一组指标，绝不影响主流程。
    """
    cross_config = config.get('cross_asset', {})
    if cross_config.get('enabled') is False:
        logger.info("Cross-asset analysis disabled by config")
        return None

    market_client = analyzers.get('market_client')
    if market_client is None:
        return None

    # 主分析已有的品种直接复用，避免重复请求
    data: Dict[str, Any] = {}
    for result in analysis_results.values():
        symbol = result.get('symbol')
        df = result.get('kline_data')
        if symbol and df is not None and not df.empty:
            data[symbol] = df

    # 增量拉取辅助品种
    auxiliary = cross_config.get(
        'auxiliary_symbols', ['XPTUSD', 'HGUSD', 'CLUSD', 'DXY']
    )
    count = int(cross_config.get('lookback_days', 400))

    for symbol in auxiliary:
        if symbol in data:
            continue
        try:
            df = market_client.get_kline(symbol, '1d', count=count)
            if df is not None and not df.empty:
                data[symbol] = df
                logger.debug(f"Cross-asset: fetched {symbol} ({len(df)} bars)")
        except Exception as e:
            # 辅助品种失败不升级为错误，仅记录
            logger.warning(f"Cross-asset: skipped {symbol} ({e})")

    if len(data) < 2:
        logger.info("Cross-asset analysis skipped: fewer than 2 instruments available")
        return None

    try:
        analyzer = analyzers.get('cross_asset') or CrossAssetAnalyzer(cross_config)
        result = analyzer.analyze(data)
    except Exception as e:
        logger.error(f"Cross-asset analysis failed: {e}")
        return None

    if not result.get('available'):
        return None

    logger.info("")
    logger.info("Cross-asset analysis:")
    for ratio in result.get('ratios', []):
        logger.info(
            f"  - {ratio['name']} ({ratio['pair']}): {ratio['value']:.2f} "
            f"({ratio['change_percent']:+.2f}%), "
            f"{ratio['percentile']:.0f}th pct of last {ratio['sample_size']}d"
        )
    for corr in result.get('correlations', []):
        logger.info(
            f"  - corr {corr['pair']}: {corr['correlation']:+.2f} "
            f"(hist {corr['historical_mean']:+.2f}, {corr['z_score']:+.1f}σ)"
        )
    for alert in result.get('alerts', []):
        logger.info(f"  ! {alert}")

    # 输出独立的联动分析报告
    report_generator = analyzers.get('report_generator')
    if report_generator is not None:
        try:
            content = report_generator.generate_cross_asset_report(result)
            path = report_generator.save_cross_asset_report(content)
            result['report_path'] = path
            logger.info(f"Cross-asset report saved to: {path}")
        except Exception as e:
            logger.warning(f"Failed to save cross-asset report: {e}")

    return result


def calculate_gold_silver_ratio(analysis_results: Dict[str, Any], logger) -> Optional[float]:
    """Calculate and log gold-silver ratio if both metals are analyzed."""
    if len(analysis_results) >= 2 and 'gold' in analysis_results and 'silver' in analysis_results:
        gold_price = analysis_results['gold']['quote'].get('price')
        silver_price = analysis_results['silver']['quote'].get('price')

        if gold_price and silver_price and silver_price > 0:
            gold_silver_ratio = gold_price / silver_price
            logger.info(f"")
            logger.info(f"Gold-Silver Ratio: {gold_silver_ratio:.1f}")
            logger.info(f"Historical average: 60-70")

            if gold_silver_ratio < 60:
                logger.info("Insight: Silver is performing strongly relative to gold")
            elif gold_silver_ratio > 70:
                logger.info("Insight: Gold is performing strongly relative to silver")
            else:
                logger.info("Insight: Gold-silver ratio is within normal range")

            return gold_silver_ratio

    return None


def send_notifications(
    notifiers: Dict[str, Any],
    analysis_results: Dict[str, Any],
    instruments_config: Dict[str, Any],
    logger
) -> None:
    """Send notifications to all available notifiers."""
    if not notifiers or not analysis_results:
        return

    logger.info(f"Sending notifications to: {', '.join(notifiers.keys())}...")

    # Prepare notification data
    reports_for_push = []
    for instrument_name, result in analysis_results.items():
        instrument_cfg = instruments_config.get(instrument_name, {})
        reports_for_push.append({
            'symbol': result['symbol'],
            'symbol_name': instrument_cfg.get('name', instrument_name),
            'quote_data': result['quote'],
            'technical_data': result['technical'],
            'patterns': result['technical'].get('patterns', {}),
            'llm_analysis': result.get('llm', {})
        })

    # Calculate gold-silver ratio
    gold_silver_ratio_value = None
    if 'gold' in analysis_results and 'silver' in analysis_results:
        gold_p = analysis_results['gold']['quote'].get('price', 0)
        silver_p = analysis_results['silver']['quote'].get('price', 0)
        if gold_p and silver_p and silver_p > 0:
            gold_silver_ratio_value = gold_p / silver_p

    # Send notifications to each available notifier
    for notifier_name, notifier in notifiers.items():
        try:
            # Send daily summary
            if notifier.send_daily_summary(reports_for_push, gold_silver_ratio_value):
                logger.info(f"{notifier_name} daily summary sent successfully")
            else:
                logger.warning(f"Failed to send {notifier_name} daily summary")
        except Exception as e:
            logger.error(f"Error sending {notifier_name} notification: {e}")

        # Send detailed reports for each instrument
        for report_data in reports_for_push:
            try:
                if notifier.send_market_report(
                    symbol_name=report_data['symbol_name'],
                    symbol=report_data['symbol'],
                    quote_data=report_data['quote_data'],
                    technical_data=report_data['technical_data'],
                    patterns=report_data.get('patterns'),
                    llm_analysis=report_data.get('llm_analysis')
                ):
                    logger.info(f"{notifier_name} report for {report_data['symbol']} sent successfully")
                else:
                    logger.warning(f"Failed to send {notifier_name} report for {report_data['symbol']}")
            except Exception as e:
                logger.error(f"Error sending {notifier_name} report for {report_data['symbol']}: {e}")


def run_backtest(
    analyzers: Dict[str, Any],
    instruments_to_analyze: List[Tuple[str, Dict[str, Any]]],
    logger
) -> None:
    """Evaluate historical signal accuracy and print a report."""
    signal_tracker = analyzers.get('signal_tracker')
    market_client = analyzers.get('market_client')

    if not signal_tracker or not market_client:
        logger.error("Signal tracker or market client unavailable")
        return

    sections = []

    for instrument_name, instrument_config in instruments_to_analyze:
        symbol = instrument_config.get('symbol')
        if not symbol:
            continue

        try:
            price_df = market_client.fetch_daily(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch prices for {symbol}: {e}")
            continue

        for field in ('technical_direction', 'llm_direction'):
            stats = signal_tracker.evaluate(symbol, price_df, field)
            label = 'Technical' if field == 'technical_direction' else 'LLM'

            logger.info(
                f"{symbol} [{label}] evaluated={stats['total_evaluated']} "
                f"win_rate={stats['win_rate']}% "
                f"avg_return={stats['avg_return_pct']}%"
            )
            sections.append(f"**{label}**\n\n" + signal_tracker.format_report(stats))

    if sections:
        output_path = Path('output/reports') / \
            f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "# 信号准确率回测报告\n\n"
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            + "\n".join(sections),
            encoding='utf-8'
        )
        logger.info(f"Backtest report saved to: {output_path}")


def main():
    """Main function"""
    # Parse command line arguments
    args = parse_arguments()

    # Setup logging
    log_level = 'DEBUG' if args.debug else 'INFO'
    logger = setup_logger(level=log_level)
    logger = get_logger('main')

    logger.info("=" * 60)
    logger.info("Metal Trend Analysis Tool Started")
    logger.info("=" * 60)

    try:
        # Load configuration
        logger.info("Loading configuration file...")
        config_loader = ConfigLoader()
        config = config_loader.load_main_config(args.config)
        logger.info("Configuration loaded successfully")

        # Initialize modules
        logger.info("Initializing modules...")
        analyzers, analyzers_success = initialize_analyzers(config, logger)
        if not analyzers_success:
            logger.error("Failed to initialize analyzers")
            sys.exit(1)

        # Determine instruments to analyze
        instruments_to_analyze = get_instruments_to_analyze(args, config)
        logger.info(f"Instruments to analyze: {[inst[0] for inst in instruments_to_analyze]}")

        # Backtest-only mode: evaluate past signals and exit
        if args.backtest:
            logger.info("Running in backtest mode (no new analysis)")
            run_backtest(analyzers, instruments_to_analyze, logger)
            logger.info("Backtest complete")
            return

        # Initialize news modules
        news_fetcher, sentiment_analyzer, news_articles = initialize_news_modules(config, logger)

        # Initialize notifiers
        notifiers = initialize_notifiers(config, logger)

        # Analyze each instrument
        analysis_results = {}
        for instrument_name, instrument_config in instruments_to_analyze:
            result = analyze_instrument(
                instrument_name,
                instrument_config,
                analyzers,
                sentiment_analyzer,
                news_articles,
                args.timeframe,
                logger,
                args.debug,
                enable_chart=not args.no_chart
            )
            if result:
                analysis_results[instrument_name] = result

        # Calculate gold-silver ratio
        gold_silver_ratio = calculate_gold_silver_ratio(analysis_results, logger)

        # Cross-asset ratios and correlations (optional enhancement)
        cross_asset_result = None
        if not args.no_cross_asset:
            cross_asset_result = run_cross_asset_analysis(
                analyzers, analysis_results, config, logger
            )

        # Send notifications
        instruments_config = config.get('instruments', {})
        send_notifications(notifiers, analysis_results, instruments_config, logger)

        # Complete
        logger.info("")
        logger.info("=" * 60)
        logger.info("Analysis Complete!")
        logger.info("=" * 60)
        logger.info("")
        logger.info(f"Total {len(analysis_results)} instruments analyzed:")
        for instrument_name, result in analysis_results.items():
            logger.info(f"  - {instrument_name}: {result['report_path']}")
            if result.get('chart_path'):
                logger.info(f"      chart: {result['chart_path']}")
        if cross_asset_result and cross_asset_result.get('report_path'):
            logger.info(f"  - cross-asset: {cross_asset_result['report_path']}")
        if notifiers:
            logger.info(f"  - Notifications sent to: {', '.join(notifiers.keys())}")
        logger.info("")

    except Exception as e:
        logger.error(f"Program error: {str(e)}")
        if args.debug:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
