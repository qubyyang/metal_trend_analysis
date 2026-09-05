"""LLM 分析层测试。

重点覆盖：
1. 输出契约校验（脏 JSON 不得污染下游）
2. prompt 注入了回测证伪结论（防止 LLM 给已证伪的技术信号背书）
3. markdown 代码块包裹的 JSON 能被正确提取
"""
import pytest
from unittest.mock import patch

from src.llm.analyzer import (
    LLMAnalyzer,
    SIGNAL_CAVEAT,
    OUTPUT_CONTRACT,
    NEWS_CAUSALITY_GUIDE,
    _as_float,
)


@pytest.fixture
def analyzer():
    with patch('src.llm.analyzer.OpenAI'):
        return LLMAnalyzer({'api_key': 'test-key'})


@pytest.fixture
def technical_data():
    return {
        'trend': 'bullish',
        'rsi': 62.3,
        'macd_signal': 'death_cross',
        'support_levels': [4300.5, 4210.0],
        'resistance_levels': [4500.0],
        'patterns': {'doji': [1], 'hammer': []},
        'signal_detail': {
            'score': 16.3,
            'effective_weight': 0.90,
            'factors': {
                'ma_alignment': {'valid': True, 'score': 0.53, 'reason': '(均线交织)'},
                'macd': {'valid': True, 'score': -0.20, 'reason': '(死叉)'},
                'volume': {'valid': False},
            },
        },
    }


@pytest.fixture
def quote_data():
    return {'price': 4430.96, 'change': 12.3, 'change_percent': 0.28,
            'low': 4400.0, 'high': 4440.0}


class TestAsFloat:
    def test_parses_numeric_strings(self):
        assert _as_float("4800") == 4800.0
        assert _as_float(4800) == 4800.0

    def test_rejects_non_numeric(self):
        assert _as_float("N/A") is None
        assert _as_float(None) is None
        assert _as_float({}) is None

    def test_rejects_bool_and_nan(self):
        # bool 是 int 子类，若不特判会把 True 变成 1.0
        assert _as_float(True) is None
        assert _as_float(float('nan')) is None


class TestJSONExtraction:
    def test_plain_json(self, analyzer):
        assert analyzer._try_parse_json('{"trend":"看涨"}') == {'trend': '看涨'}

    def test_markdown_fenced_json(self, analyzer):
        raw = '分析如下:\n```json\n{"trend":"看跌"}\n```\n以上。'
        assert analyzer._try_parse_json(raw) == {'trend': '看跌'}

    def test_json_with_surrounding_text(self, analyzer):
        raw = '结论：{"trend":"中性"} 仅供参考'
        assert analyzer._try_parse_json(raw) == {'trend': '中性'}

    def test_returns_none_on_garbage(self, analyzer):
        assert analyzer._try_parse_json('完全不是 JSON') is None
        assert analyzer._try_parse_json('') is None
        assert analyzer._try_parse_json('{坏掉的 json') is None


class TestOutputContract:
    """契约优先于信任：脏数据必须降级，不能流向报告与信号记录。"""

    def test_valid_payload_passes_clean(self, analyzer):
        raw = ('{"trend":"看涨","suggestion":"回调做多","risk_level":"中",'
               '"confidence":"高","logic":"美联储降息","key_points":["降息"],'
               '"target_price":{"short_term":4500,"medium_term":4800}}')
        result = analyzer._parse_analysis(raw)
        assert result['parse_mode'] == 'json'
        a = result['analysis']
        assert a['trend'] == '看涨'
        assert a['confidence'] == '高'
        assert a['target_price']['short_term'] == 4500.0
        assert a['schema_warnings'] == []

    def test_english_enums_normalized(self, analyzer):
        raw = '{"trend":"bullish","risk_level":"high","confidence":"low"}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert (a['trend'], a['risk_level'], a['confidence']) == ('看涨', '高', '低')
        assert a['schema_warnings'] == []

    def test_illegal_enums_downgraded(self, analyzer):
        raw = '{"trend":"暴涨","risk_level":99,"confidence":null}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert a['trend'] == '中性'
        assert a['risk_level'] == '中'
        assert a['confidence'] == '低'
        assert len(a['schema_warnings']) == 3

    def test_string_numbers_coerced_in_target_price(self, analyzer):
        raw = '{"trend":"看涨","target_price":{"short_term":"4500","medium_term":"x"}}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert a['target_price']['short_term'] == 4500.0
        assert a['target_price']['medium_term'] is None

    def test_malformed_target_price_ignored(self, analyzer):
        raw = '{"trend":"中性","target_price":"不确定"}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert a['target_price'] == {'short_term': None, 'medium_term': None}
        assert any('target_price' in w for w in a['schema_warnings'])

    def test_high_confidence_without_evidence_is_downgraded(self, analyzer):
        """纪律约束：技术面已被证伪，无支撑要点就不许报高置信度。"""
        raw = '{"trend":"看跌","confidence":"高","key_points":[],"logic":"直觉"}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert a['confidence'] == '中'
        assert any('下调' in w for w in a['schema_warnings'])

    def test_key_points_string_wrapped_into_list(self, analyzer):
        raw = '{"trend":"看涨","key_points":"单条要点"}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert a['key_points'] == ['单条要点']

    def test_key_points_capped_at_five(self, analyzer):
        raw = '{"trend":"看涨","key_points":["1","2","3","4","5","6","7"]}'
        a = analyzer._parse_analysis(raw)['analysis']
        assert len(a['key_points']) == 5

    def test_text_fallback_forces_low_confidence(self, analyzer):
        """正则抽取本身不可靠，置信度必须标低。"""
        result = analyzer._parse_analysis('市场看涨，建议买入，风险较低')
        assert result['parse_mode'] == 'text'
        assert result['analysis']['confidence'] == '低'
        assert result['analysis']['schema_warnings']

    def test_never_emits_na_trend(self, analyzer):
        """'N/A' 会污染 signal_tracker 的方向归一，必须杜绝。"""
        for raw in ('', '完全无法解析', '{}', '{"trend":123}'):
            a = analyzer._parse_analysis(raw)['analysis']
            assert a.get('trend') != 'N/A'


class TestPromptConstruction:
    def test_injects_backtest_falsification(self, analyzer, quote_data, technical_data):
        """最关键的一条：必须告知 LLM 技术信号已被证伪。"""
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], None)
        assert SIGNAL_CAVEAT in prompt
        assert '与随机无统计显著差异' in prompt
        assert '不得把技术评分本身当作看涨/看跌的独立依据' in prompt

    def test_includes_output_contract(self, analyzer, quote_data, technical_data):
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], None)
        assert OUTPUT_CONTRACT in prompt
        assert 'evidence_quality' in prompt

    def test_renders_factor_detail(self, analyzer, quote_data, technical_data):
        """LLM 应看到因子构成，而非只有一个结论分数。"""
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], None)
        assert '均线排列: +0.53' in prompt
        assert 'MACD: -0.20' in prompt
        assert '成交量: 数据不可用，已剔除' in prompt
        assert '加权总分: +16.3 / 100' in prompt

    def test_news_causality_guide_when_news_present(
            self, analyzer, quote_data, technical_data):
        news = [{'title': '美联储维持利率不变', 'source': 'WSJ', 'published': '2026-09-04'}]
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, news, None)
        assert NEWS_CAUSALITY_GUIDE in prompt
        assert '美联储维持利率不变' in prompt
        assert '反应滞后型' in prompt

    def test_no_news_warns_low_confidence(self, analyzer, quote_data, technical_data):
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], None)
        assert '置信度应当标为' in prompt

    def test_gold_silver_ratio_rendered(self, analyzer, quote_data, technical_data):
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], 82.5)
        assert '82.5' in prompt
        assert '避险需求主导' in prompt

    def test_handles_missing_quote_fields(self, analyzer, technical_data):
        """行情字段缺失或为 'N/A' 时不应抛异常。"""
        prompt = analyzer._build_analysis_prompt(
            'XAGUSD', {'price': 'N/A', 'change': None}, technical_data, [], None)
        assert 'XAGUSD' in prompt
        assert OUTPUT_CONTRACT in prompt

    def test_symbol_name_mapping(self, analyzer, quote_data, technical_data):
        gold = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, technical_data, [], None)
        silver = analyzer._build_analysis_prompt(
            'XAGUSD', quote_data, technical_data, [], None)
        assert '黄金（XAUUSD）' in gold
        assert '白银（XAGUSD）' in silver

    def test_empty_factor_detail_is_safe(self, analyzer, quote_data):
        prompt = analyzer._build_analysis_prompt(
            'XAUUSD', quote_data, {'trend': 'neutral'}, [], None)
        assert '因子评分明细' not in prompt
        assert OUTPUT_CONTRACT in prompt


class TestNoDeadCode:
    def test_legacy_build_prompt_removed(self, analyzer):
        """_build_prompt 曾是从未被调用的 215 行死代码，已合并删除。"""
        assert not hasattr(analyzer, '_build_prompt')
