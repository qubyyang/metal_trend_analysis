"""
Metal Trend Analysis Tool - Main Program
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import ConfigLoader
from src.utils.logger import setup_logger, get_logger
from src.data_fetchers.itick_client import ITickClient
from src.analyzers.technical import TechnicalAnalyzer
from src.analyzers.patterns import PatternRecognizer
from src.llm.analyzer import LLMAnalyzer
from src.reporting.generator import ReportGenerator
from src.notification.feishu import FeishuNotifier


def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Metal Trend Analysis Tool')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Configuration file path')
    parser.add_argument('--instrument', type=str, default='all',
                        choices=['all', 'gold', 'silver', 'XAUUSD', 'XAGUSD'],
                        help='Instrument to analyze')
    parser.add_argument('--timeframe', type=str, default='5m',
                        help='Timeframe (1m, 5m - iTick API supported)')
    parser.add_argument('--debug', action='store_true',
                        help='Debug mode')

    args = parser.parse_args()

    # Setup logging
    log_level = 'DEBUG' if args.debug else 'INFO'
    logger = setup_logger(level=log_level)
    logger = get_logger('main')

    logger.info("=" * 60)
    logger.info("Metal Trend Analysis Tool Started")
    logger.info("=" * 60)

    try:
        # 1. Load configuration
        logger.info("Loading configuration file...")
        config_loader = ConfigLoader()
        config = config_loader.load_main_config(args.config)

        logger.info(f"Configuration loaded successfully")

        # 2. Initialize modules
        logger.info("Initializing modules...")

        # iTick client
        itick_config = config.get('api', {}).get('itick', {})
        itick_client = ITickClient(itick_config)
        logger.info("iTick client initialized successfully")

        # Technical analyzer
        indicators_config = config.get('indicators', {})
        technical_analyzer = TechnicalAnalyzer(indicators_config)
        logger.info("Technical analyzer initialized successfully")

        # Pattern recognizer
        pattern_recognizer = PatternRecognizer()
        logger.info("Pattern recognizer initialized successfully")

        # LLM analyzer
        llm_config = config.get('llm', {})
        llm_analyzer = LLMAnalyzer(llm_config)
        logger.info("LLM analyzer initialized successfully")

        # Report generator
        reports_config = config.get('reports', {})
        report_generator = ReportGenerator(reports_config)
        logger.info("Report generator initialized successfully")

        # Feishu notifier (飞书推送)
        notification_config = config.get('notification', {})
        feishu_notifier = None
        if notification_config.get('enabled', False):
            feishu_config = notification_config.get('channels', {}).get('feishu', {})
            if feishu_config.get('enabled', False):
                feishu_webhook = feishu_config.get('webhook_url', '')
                feishu_notifier = FeishuNotifier(
                    webhook_url=feishu_webhook,
                    timeout=feishu_config.get('timeout', 30)
                )
                if feishu_notifier.is_available():
                    logger.info("Feishu notifier initialized successfully")
                else:
                    logger.warning("Feishu webhook URL not configured, notifications disabled")
                    feishu_notifier = None

        # 3. Determine instruments to analyze
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

        logger.info(f"Instruments to analyze: {[inst[0] for inst in instruments_to_analyze]}")

        # 4. Analyze each instrument
        analysis_results = {}

        for instrument_name, instrument_config in instruments_to_analyze:
            if not instrument_config.get('enabled', True):
                logger.info(f"{instrument_name} is not enabled, skipping")
                continue

            symbol = instrument_config.get('symbol')
            symbol_name = instrument_config.get('name')
            region = instrument_config.get('region', 'GB')

            logger.info(f"")
            logger.info(f"Starting analysis for {symbol_name} ({symbol})...")
            logger.info("-" * 60)

            try:
                # 5.1 Get real-time quote
                logger.info(f"Fetching real-time quote for {symbol}...")
                quote_data = itick_client.get_quote(symbol, region)

                if not quote_data:
                    logger.error(f"Failed to fetch quote for {symbol}")
                    continue

                logger.info(f"Current price: ${quote_data.get('price')}")
                logger.info(f"Change: {quote_data.get('change')} ({quote_data.get('change_percent')}%)")

                # 5.2 Get K-line data
                logger.info(f"Fetching K-line data for {symbol}...")
                kline_data = itick_client.get_kline(symbol, args.timeframe)

                if kline_data.empty:
                    logger.error(f"Failed to fetch K-line data for {symbol}")
                    continue

                logger.info(f"Fetched {len(kline_data)} K-line records")

                # Save raw data
                itick_client.save_raw_data(kline_data, symbol, args.timeframe)

                # 5.3 Calculate technical indicators
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

                # 5.4 Identify K-line patterns
                logger.info("Identifying K-line patterns...")
                patterns = pattern_recognizer.detect_patterns(kline_data)
                pattern_summary = pattern_recognizer.get_pattern_summary(patterns)

                logger.info("K-line patterns:")
                if pattern_summary:
                    for line in pattern_summary.split('\n'):
                        if line.strip():
                            logger.info(f"  {line}")

                technical_result['patterns'] = patterns

                # 5.5 LLM comprehensive analysis
                logger.info("Performing LLM comprehensive analysis...")
                llm_result = llm_analyzer.analyze_market(
                    symbol,
                    quote_data,
                    technical_result,
                    []  # news_articles disabled
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

                # 5.6 Generate report
                logger.info("Generating analysis report...")
                report_content = report_generator.generate_markdown_report(
                    symbol,
                    symbol_name,
                    quote_data,
                    technical_result,
                    [],  # news_articles disabled
                    llm_result
                )

                report_path = report_generator.save_report(report_content, symbol, args.timeframe)
                logger.info(f"Report saved to: {report_path}")

                # Save analysis results
                analysis_results[instrument_name] = {
                    'symbol': symbol,
                    'quote': quote_data,
                    'technical': technical_result,
                    'llm': llm_result,
                    'report_path': report_path
                }

                logger.info(f"{symbol_name} analysis completed")
                logger.info("-" * 60)

            except Exception as e:
                logger.error(f"Error analyzing {symbol_name}: {str(e)}")
                if args.debug:
                    import traceback
                    logger.error(traceback.format_exc())

        # 6. Calculate gold-silver ratio
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

        # 7. Send Feishu notifications (飞书推送)
        # 只有当 feishu_notifier 可用（即 webhook_url 已配置）时才发送
        if feishu_notifier and analysis_results:
            logger.info("")
            logger.info("Sending Feishu notifications...")

            # 准备推送数据
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

            # 计算黄金白银比
            gold_silver_ratio_value = None
            if 'gold' in analysis_results and 'silver' in analysis_results:
                gold_p = analysis_results['gold']['quote'].get('price', 0)
                silver_p = analysis_results['silver']['quote'].get('price', 0)
                if gold_p and silver_p and silver_p > 0:
                    gold_silver_ratio_value = gold_p / silver_p

            # 发送每日汇总报告
            try:
                if feishu_notifier.send_daily_summary(reports_for_push, gold_silver_ratio_value):
                    logger.info("Feishu daily summary sent successfully")
                else:
                    logger.warning("Failed to send Feishu daily summary")
            except Exception as e:
                logger.error(f"Error sending Feishu notification: {e}")

            # 发送各品种详细报告（可选）
            for report_data in reports_for_push:
                try:
                    if feishu_notifier.send_market_report(
                        symbol_name=report_data['symbol_name'],
                        symbol=report_data['symbol'],
                        quote_data=report_data['quote_data'],
                        technical_data=report_data['technical_data'],
                        patterns=report_data.get('patterns'),
                        llm_analysis=report_data.get('llm_analysis')
                    ):
                        logger.info(f"Feishu report for {report_data['symbol']} sent successfully")
                    else:
                        logger.warning(f"Failed to send Feishu report for {report_data['symbol']}")
                except Exception as e:
                    logger.error(f"Error sending Feishu report for {report_data['symbol']}: {e}")

        # 8. Complete
        logger.info("")
        logger.info("=" * 60)
        logger.info("Analysis Complete!")
        logger.info("=" * 60)
        logger.info(f"")
        logger.info(f"Total {len(analysis_results)} instruments analyzed:")
        for instrument_name, result in analysis_results.items():
            logger.info(f"  - {instrument_name}: {result['report_path']}")
        if feishu_notifier and feishu_notifier.is_available():
            logger.info(f"  - Feishu notifications sent")
        logger.info("")

    except Exception as e:
        logger.error(f"Program error: {str(e)}")
        if args.debug:
            import traceback
            logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
