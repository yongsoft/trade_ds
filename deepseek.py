from logging import Logger
import os
import time
from typing import Any
import schedule
from openai import OpenAI
import ccxt
import pandas as pd
import re
from dotenv import load_dotenv
import json
import requests
from datetime import datetime, timedelta
import logging
import traceback
import sys
from pathlib import Path

# 配置日志系统
def setup_logger():
    # 创建logs目录（如果不存在）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 生成日志文件名（包含日期）
    log_file = log_dir / f"trading_{datetime.now().strftime('%Y%m%d')}.log"

    # 从环境变量读取日志级别，默认为INFO
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    log_level = log_level_map.get(log_level_str, logging.INFO)

    # 配置日志格式
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 配置根日志记录器
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger()

load_dotenv()

# 初始化日志记录器
logger: Logger = setup_logger()
logger.info("初始化交易机器人...")


# 检查必要的环境变量
if not os.getenv('DEEPSEEK_API_KEY'):
    logger.error("缺少DEEPSEEK_API_KEY环境变量，请在.env文件中配置")
    sys.exit(1)

if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_SECRET'):
    logger.warning("缺少币安API密钥，如果不是测试模式，交易将无法执行")

# 初始化DeepSeek客户端
try:
    deepseek_client = OpenAI(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url="https://api.deepseek.com"
    )
    logger.info("DeepSeek客户端初始化成功")
except Exception as e:
    logger.error(f"DeepSeek客户端初始化失败: {e}")
    sys.exit(1)

try:
    exchange = ccxt.binance({
        'options': {'defaultType': 'future'},
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET'),
    })
    logger.info("币安交易所客户端初始化成功")
except Exception as e:
    logger.error(f"币安交易所客户端初始化失败: {e}")
    sys.exit(1)

# 交易参数配置
TRADE_CONFIG = {
    'symbol': 'BTC/USDT',
    'amount': 0.002,  # 交易数量 (BTC)
    'leverage': 10,  # 杠杆倍数
    'timeframe': '15m',  # 使用1小时K线，可改为15m
    'test_mode': False,  # 测试模式
    'data_points': 96,  # 24小时数据（96根15分钟K线）
    'analysis_periods': {
        'short_term': 20,  # 短期均线
        'medium_term': 50,  # 中期均线
        'long_term': 96  # 长期趋势
    },
    # 新增智能仓位参数
    'position_management': {
        'enable_intelligent_position': True,  # 🆕 新增：是否启用智能仓位管理
        'base_usdt_amount': 100,  # USDT投入下单基数
        'high_confidence_multiplier': 1,
        'medium_confidence_multiplier': 0.8,
        'low_confidence_multiplier': 0.5,
        'position_ratio_max': 0.99,  # 总最大仓位比例
        'position_ratio_single_trade': 0.2,
        'trend_strength_multiplier': 1.0
    }
}
logger.info(f"交易配置: {json.dumps(TRADE_CONFIG, ensure_ascii=False)}")

# 全局变量存储历史数据
price_history = []
signal_history = []
position = None
balance_latest: Any = None


def setup_exchange():
    """设置交易所参数"""
    global balance_latest
    try:
        # 获取合约规格信息
        logger.info("获取BTC合约规格...")
        markets = exchange.load_markets()
        btc_market = markets[TRADE_CONFIG['symbol']]
        #logger.info(f"市场参数: {markets}")

        # 设置杠杆
        exchange.set_leverage(TRADE_CONFIG['leverage'], TRADE_CONFIG['symbol'])
        logger.info(f"设置杠杆倍数: {TRADE_CONFIG['leverage']}x")

        # 获取余额
        balance_latest = exchange.fetch_balance()
        usdt_balance = balance_latest['USDT']['free']
        logger.info(f"当前USDT余额: {usdt_balance:.2f}")

        # 获取当前持仓状态
        current_pos = get_current_position()
        if current_pos:
            logger.info(f"当前持仓: {current_pos['side']}仓 数量:{current_pos['size']}")
        else:
            logger.info("当前无持仓")

        return True
    except ccxt.NetworkError as e:
        logger.error(f"交易所网络连接失败: {e}")
        return False
    except ccxt.ExchangeError as e:
        logger.error(f"交易所API错误: {e}")
        return False
    except Exception as e:
        logger.error(f"交易所设置失败: {e}")
        logger.debug(traceback.format_exc())
        return False


def calculate_technical_indicators(df):
    """计算技术指标"""
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # 指数移动平均线
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # 相对强弱指数 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 支撑阻力位
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        # 填充NaN值
        df = df.bfill().ffill()

        return df
    except Exception as e:
        logger.error(f"技术指标计算失败: {e}")
        return df


def get_support_resistance_levels(df, lookback=20):
    """计算支撑阻力位"""
    try:
        recent_high = df['high'].tail(lookback).max()
        recent_low = df['low'].tail(lookback).min()
        current_price = df['close'].iloc[-1]

        resistance_level = recent_high
        support_level = recent_low

        # 动态支撑阻力（基于布林带）
        bb_upper = df['bb_upper'].iloc[-1]
        bb_lower = df['bb_lower'].iloc[-1]

        return {
            'static_resistance': resistance_level,
            'static_support': support_level,
            'dynamic_resistance': bb_upper,
            'dynamic_support': bb_lower,
            'price_vs_resistance': ((resistance_level - current_price) / current_price) * 100,
            'price_vs_support': ((current_price - support_level) / support_level) * 100
        }
    except Exception as e:
        logger.error(f"支撑阻力计算失败: {e}")
        return {}


def get_sentiment_indicators():
    """获取情绪指标"""
    try:
        API_URL = "https://service.cryptoracle.network/openapi/v2/endpoint"
        API_KEY = "7ad48a56-8730-4238-a714-eebc30834e3e"

        # 获取最近4小时数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=4)

        request_body = {
            "apiKey": API_KEY,
            "endpoints": ["CO-A-02-01", "CO-A-02-02"],
            "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "timeType": "15m",
            "token": ["BTC"]
        }

        headers = {"Content-Type": "application/json", "X-API-KEY": API_KEY}
        response = requests.post(API_URL, json=request_body, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 and data.get("data"):
                time_periods = data["data"][0]["timePeriods"]

                for period in time_periods:
                    period_data = period.get("data", [])
                    sentiment = {}
                    valid_data_found = False

                    for item in period_data:
                        endpoint = item.get("endpoint")
                        value = item.get("value", "").strip()

                        if value:
                            try:
                                if endpoint in ["CO-A-02-01", "CO-A-02-02"]:
                                    sentiment[endpoint] = float(value)
                                    valid_data_found = True
                            except (ValueError, TypeError):
                                continue

                    if valid_data_found and "CO-A-02-01" in sentiment and "CO-A-02-02" in sentiment:
                        positive = sentiment['CO-A-02-01']
                        negative = sentiment['CO-A-02-02']
                        net_sentiment = positive - negative

                        data_delay = int((datetime.now() - datetime.strptime(
                            period['startTime'], '%Y-%m-%d %H:%M:%S')).total_seconds() // 60)

                        logger.info(f"使用情绪数据时间: {period['startTime']} (延迟: {data_delay}分钟)")

                        return {
                            'positive_ratio': positive,
                            'negative_ratio': negative,
                            'net_sentiment': net_sentiment,
                            'data_time': period['startTime'],
                            'data_delay_minutes': data_delay
                        }

                logger.warning("所有时间段数据都为空")
                return None

        return None
    except Exception as e:
        logger.error(f"情绪指标获取失败: {e}")
        return None


def get_market_trend(df):
    """判断市场趋势"""
    try:
        current_price = df['close'].iloc[-1]

        # 多时间框架趋势分析
        trend_short = "上涨" if current_price > df['sma_20'].iloc[-1] else "下跌"
        trend_medium = "上涨" if current_price > df['sma_50'].iloc[-1] else "下跌"

        # MACD趋势
        macd_trend = "bullish" if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else "bearish"

        # 综合趋势判断
        if trend_short == "上涨" and trend_medium == "上涨":
            overall_trend = "强势上涨"
        elif trend_short == "下跌" and trend_medium == "下跌":
            overall_trend = "强势下跌"
        else:
            overall_trend = "震荡整理"

        return {
            'short_term': trend_short,
            'medium_term': trend_medium,
            'macd': macd_trend,
            'overall': overall_trend,
            'rsi_level': df['rsi'].iloc[-1]
        }
    except Exception as e:
        logger.error(f"趋势分析失败: {e}")
        return {}


def get_btc_ohlcv():
    """增强版：获取BTC K线数据并计算技术指标"""
    try:
        logger.info(f"获取{TRADE_CONFIG['symbol']}的{TRADE_CONFIG['timeframe']}K线数据")
        # 获取K线数据
        ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'],
                                     limit=TRADE_CONFIG['data_points'])

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # 计算技术指标
        df = calculate_technical_indicators(df)

        current_data = df.iloc[-1]
        previous_data = df.iloc[-2]

        # 获取技术分析数据
        trend_analysis = get_market_trend(df)
        levels_analysis = get_support_resistance_levels(df)

        result = {
            'price': current_data['close'],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'high': current_data['high'],
            'low': current_data['low'],
            'volume': current_data['volume'],
            'timeframe': TRADE_CONFIG['timeframe'],
            'price_change': ((current_data['close'] - previous_data['close']) / previous_data['close']) * 100,
            'kline_data': df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10).to_dict('records'),
            'technical_data': {
                'sma_5': current_data.get('sma_5', 0),
                'sma_20': current_data.get('sma_20', 0),
                'sma_50': current_data.get('sma_50', 0),
                'rsi': current_data.get('rsi', 0),
                'macd': current_data.get('macd', 0),
                'macd_signal': current_data.get('macd_signal', 0),
                'macd_histogram': current_data.get('macd_histogram', 0),
                'bb_upper': current_data.get('bb_upper', 0),
                'bb_lower': current_data.get('bb_lower', 0),
                'bb_position': current_data.get('bb_position', 0),
                'volume_ratio': current_data.get('volume_ratio', 0)
            },
            'trend_analysis': trend_analysis,
            'levels_analysis': levels_analysis,
            'full_data': df
        }

        logger.info(f"当前价格: ${result['price']:,.2f}, 价格变化: {result['price_change']:+.2f}%")
        return result
    except ccxt.NetworkError as e:
        logger.error(f"获取K线数据网络错误: {e}")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"获取K线数据交易所错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        logger.debug(traceback.format_exc())
        return None


def get_current_position():
    """获取当前持仓情况"""
    try:
        logger.info(f"获取{TRADE_CONFIG['symbol']}当前持仓情况")
        positions = exchange.fetch_positions([TRADE_CONFIG['symbol']])

        # 标准化配置的交易对符号用于比较
        config_symbol_normalized = 'BTC/USDT:USDT'

        for pos in positions:
            # 比较标准化的符号
            if pos['symbol'] == config_symbol_normalized:
                # 获取持仓数量
                position_amt = 0
                if 'positionAmt' in pos.get('info', {}):
                    position_amt = float(pos['info']['positionAmt'])
                elif 'contracts' in pos:
                    # 使用 contracts 字段，根据 side 确定方向
                    contracts = float(pos['contracts'])
                    if pos.get('side') == 'short':
                        position_amt = -contracts
                    else:
                        position_amt = contracts

                logger.debug(f"持仓量: {position_amt}")

                if position_amt != 0:  # 有持仓
                    side = 'long' if position_amt > 0 else 'short'
                    position_info = {
                        'side': side,
                        'size': abs(position_amt),
                        'entry_price': float(pos.get('entryPrice', 0)),
                        'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                        'position_amt': position_amt,
                        'symbol': pos['symbol']  # 返回实际的symbol用于调试
                    }
                    logger.info(f"当前持仓: {side}仓, 数量: {abs(position_amt)}, 盈亏: {float(pos.get('unrealizedPnl', 0)):.2f}USDT")
                    return position_info

        logger.info("当前无持仓")
        return None

    except ccxt.NetworkError as e:
        logger.error(f"获取持仓网络错误: {e}")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"获取持仓交易所错误: {e}")
        return None
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        logger.debug(traceback.format_exc())
        return None


def generate_technical_analysis_text(price_data):
    """生成技术分析文本"""
    if 'technical_data' not in price_data:
        return "技术指标数据不可用"

    tech = price_data['technical_data']
    trend = price_data.get('trend_analysis', {})
    levels = price_data.get('levels_analysis', {})

    # 检查数据有效性
    def safe_float(value, default=0):
        return float(value) if value and pd.notna(value) else default

    analysis_text = f"""
    【技术指标分析】
    📈 移动平均线:
    - 5周期: {safe_float(tech['sma_5']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_5'])) / safe_float(tech['sma_5']) * 100:+.2f}%
    - 20周期: {safe_float(tech['sma_20']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_20'])) / safe_float(tech['sma_20']) * 100:+.2f}%
    - 50周期: {safe_float(tech['sma_50']):.2f} | 价格相对: {(price_data['price'] - safe_float(tech['sma_50'])) / safe_float(tech['sma_50']) * 100:+.2f}%

    🎯 趋势分析:
    - 短期趋势: {trend.get('short_term', 'N/A')}
    - 中期趋势: {trend.get('medium_term', 'N/A')}
    - 整体趋势: {trend.get('overall', 'N/A')}
    - MACD方向: {trend.get('macd', 'N/A')}

    📊 动量指标:
    - RSI: {safe_float(tech['rsi']):.2f} ({'超买' if safe_float(tech['rsi']) > 70 else '超卖' if safe_float(tech['rsi']) < 30 else '中性'})
    - MACD: {safe_float(tech['macd']):.4f}
    - 信号线: {safe_float(tech['macd_signal']):.4f}

    🎚️ 布林带位置: {safe_float(tech['bb_position']):.2%} ({'上部' if safe_float(tech['bb_position']) > 0.7 else '下部' if safe_float(tech['bb_position']) < 0.3 else '中部'})

    💰 关键水平:
    - 静态阻力: {safe_float(levels.get('static_resistance', 0)):.2f}
    - 静态支撑: {safe_float(levels.get('static_support', 0)):.2f}
    """
    return analysis_text


def safe_json_parse(json_str):
    """安全解析JSON，处理格式不规范的情况"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            # 修复常见的JSON格式问题
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败，原始内容: {json_str}")
            logger.error(f"错误详情: {e}")
            return None


def create_fallback_signal(price_data):
    """创建备用交易信号"""
    return {
        "signal": "HOLD",
        "reason": "因技术分析暂时不可用，采取保守策略",
        "stop_loss": price_data['price'] * 0.98,
        "take_profit": price_data['price'] * 1.02,
        "confidence": "LOW",
        "is_fallback": True
    }


def analyze_with_deepseek(price_data):
    """使用DeepSeek分析市场并生成交易信号（增强版）"""

    global balance_latest
    # 生成技术分析文本
    technical_analysis = generate_technical_analysis_text(price_data)

    # 构建K线数据文本
    kline_text = f"【最近5根{TRADE_CONFIG['timeframe']} K线数据】\n"
    for i, kline in enumerate(price_data['kline_data'][-5:]):
        trend = "阳线" if kline['close'] > kline['open'] else "阴线"
        change = ((kline['close'] - kline['open']) / kline['open']) * 100
        kline_text += f"K线{i + 1}: {trend} 开盘:{kline['open']:.2f} 收盘:{kline['close']:.2f} 涨跌:{change:+.2f}%\n"

    # 添加上次交易信号
    signal_text = ""
    if signal_history:
        last_signal = signal_history[-1]
        signal_text = f"\n【上次交易信号】\n信号: {last_signal.get('signal', 'N/A')}\n信心: {last_signal.get('confidence', 'N/A')}"

    # 获取情绪数据
    sentiment_data = get_sentiment_indicators()
    if sentiment_data:
        sign = '+' if sentiment_data['net_sentiment'] >= 0 else ''
        sentiment_text = f"【市场情绪】乐观{sentiment_data['positive_ratio']:.1%} 悉观{sentiment_data['negative_ratio']:.1%} 净值{sign}{sentiment_data['net_sentiment']:.3f}"
    else:
        sentiment_text = "【市场情绪】数据暂不可用"

    # 添加当前持仓信息
    current_pos = get_current_position()

    gain_ratio = current_pos['unrealized_pnl'] *100/ balance_latest['USDT']['used'] if current_pos else 0
    position_text = "无持仓" if not current_pos else f"{current_pos['side']}仓, 数量: {current_pos['size']}, 本金: {balance_latest['USDT']['used']} 盈亏: {current_pos['unrealized_pnl']:.2f}USDT ,盈利比率： {gain_ratio:.2f}%"


    prompt = f"""
    你是一个专业的加密货币交易分析师。请基于以下BTC/USDT {TRADE_CONFIG['timeframe']}周期数据进行分析：

    {kline_text}

    {technical_analysis}

    {signal_text}

    {sentiment_text}

    【当前行情】
    - 当前价格: ${price_data['price']:,.2f}
    - 时间: {price_data['timestamp']}
    - 本K线最高: ${price_data['high']:,.2f}
    - 本K线最低: ${price_data['low']:,.2f}
    - 本K线成交量: {price_data['volume']:.2f} BTC
    - 价格变化: {price_data['price_change']:+.2f}%
    - 当前持仓: {position_text}

    【防频繁交易重要原则】
    1. **趋势持续性优先**: 不要因单根K线或短期波动改变整体趋势判断
    2. **持仓稳定性**: 除非趋势明确强烈反转，否则保持现有持仓方向
    3. **反转确认**: 需要至少2-3个技术指标同时确认趋势反转才改变信号
    4. **成本意识**: 减少不必要的仓位调整，每次交易都有成本

    【交易指导原则 - 必须遵守】
    1. **技术分析主导** (权重60%)：趋势、支撑阻力、K线形态是主要依据
    2. **市场情绪辅助** (权重30%)：情绪数据用于验证技术信号，不能单独作为交易理由
    - 情绪与技术同向 → 增强信号信心
    - 情绪与技术背离 → 以技术分析为主，情绪仅作参考
    - 情绪数据延迟 → 降低权重，以实时技术指标为准
    3. **风险管理** (权重10%)：考虑持仓、盈亏状况和止损位置， 在盈利超过20%的时候，考虑止盈， 在亏损超过10%的时候，考虑止亏。 
    4. **趋势跟随**: 明确趋势出现时立即行动，不要过度等待
    5. 因为做的是btc，做多权重可以大一点点
    6. **信号明确性**:
    - 强势上涨趋势 → BUY信号
    - 强势下跌趋势 → SELL信号
    - 仅在窄幅震荡、无明确方向时 → HOLD信号
    7. **技术指标权重**:
    - 趋势(均线排列) > RSI > MACD > 布林带
    - 价格突破关键支撑/阻力位是重要信号

    【当前技术状况分析】
    - 整体趋势: {price_data['trend_analysis'].get('overall', 'N/A')}
    - 短期趋势: {price_data['trend_analysis'].get('short_term', 'N/A')}
    - RSI状态: {price_data['technical_data'].get('rsi', 0):.1f} ({'超买' if price_data['technical_data'].get('rsi', 0) > 70 else '超卖' if price_data['technical_data'].get('rsi', 0) < 30 else '中性'})
    - MACD方向: {price_data['trend_analysis'].get('macd', 'N/A')}

    【重要】请基于技术分析做出明确判断，避免因过度谨慎而错过趋势行情！

    【分析要求】
    基于以上分析，请给出明确的交易信号

    请用以下JSON格式回复：
    {{
        "signal": "BUY|SELL|HOLD",
        "reason": "简要分析理由(包含趋势判断和技术依据)",
        "stop_loss": 具体价格,
        "take_profit": 具体价格,
        "confidence": "HIGH|MEDIUM|LOW"
    }}
    """

    #logger.info("发送分析请求到DeepSeek")
    logger.info(f"DeepSeek请求内容: {prompt}")

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system",
                 "content": f"您是一位专业的交易员，专注于{TRADE_CONFIG['timeframe']}周期趋势分析。请结合K线形态和技术指标做出判断，并严格遵循json格式要求。"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.1
        )

        # 安全解析JSON
        result = response.choices[0].message.content
        logger.debug(f"DeepSeek原始回复: {result}")

        # 提取JSON部分
        start_idx = result.find('{')
        end_idx = result.rfind('}') + 1

        if start_idx != -1 and end_idx != 0:
            json_str = result[start_idx:end_idx]
            signal_data = safe_json_parse(json_str)

            if signal_data is None:
                signal_data = create_fallback_signal(price_data)
        else:
            signal_data = create_fallback_signal(price_data)

        # 验证必需字段
        required_fields = ['signal', 'reason', 'stop_loss', 'take_profit', 'confidence']
        if not all(field in signal_data for field in required_fields):
            signal_data = create_fallback_signal(price_data)

        # 保存信号到历史记录
        signal_data['timestamp'] = price_data['timestamp']
        signal_history.append(signal_data)
        if len(signal_history) > 30:
            signal_history.pop(0)

        # 信号统计
        signal_count = len([s for s in signal_history if s.get('signal') == signal_data['signal']])
        total_signals = len(signal_history)
        logger.info(f"信号统计: {signal_data['signal']} (最近{total_signals}次中出现{signal_count}次)")

        # 信号连续性检查
        if len(signal_history) >= 3:
            last_three = [s['signal'] for s in signal_history[-3:]]
            if len(set(last_three)) == 1:
                logger.warning(f"注意：连续3次{signal_data['signal']}信号")

        logger.info(f"解析交易信号成功: {signal_data['signal']}, 信心: {signal_data['confidence']}")
        return signal_data

    except json.JSONDecodeError as e:
        logger.error(f"JSON解析错误: {e}")
        return create_fallback_signal(price_data)
    except Exception as e:
        logger.error(f"DeepSeek分析失败: {e}")
        logger.debug(traceback.format_exc())
        return create_fallback_signal(price_data)


def calculate_intelligent_position(signal_data, price_data, current_position):
    """计算智能仓位大小"""
    global balance_latest
    config = TRADE_CONFIG['position_management']


    # 如果禁用智能仓位，使用固定仓位
    if not config.get('enable_intelligent_position', True):
        fixed_amount = TRADE_CONFIG['amount']
        logger.info(f"🔧 智能仓位已禁用，使用固定仓位: {fixed_amount} BTC")
        return fixed_amount
    if signal_data['signal']== 'HOLD':
        return TRADE_CONFIG['amount']
    try:
        balance_latest = exchange.fetch_balance()
        usdt_balance = balance_latest['USDT']['free']
        usdt_used = balance_latest['USDT']['used']
        usdt_total = usdt_used + usdt_balance
        base_usdt = config['base_usdt_amount']

        position_ratio = usdt_used/usdt_total

        logger.info(f"仓位情况 USDT： Used : {usdt_used:.2f} 可用: {usdt_balance:.2f}, 总共: {usdt_total:.2f}, 仓位比: {position_ratio:.2f}, 下单基数{base_usdt}")

        # 根据信心程度调整
        confidence_multiplier = {
            'HIGH': config['high_confidence_multiplier'],
            'MEDIUM': config['medium_confidence_multiplier'],
            'LOW': config['low_confidence_multiplier']
        }.get(signal_data['confidence'], 1.0)

        # 根据趋势强度调整
        trend = price_data['trend_analysis'].get('overall', '震荡整理')
        if trend in ['强势上涨', '强势下跌']:
            trend_multiplier = config['trend_strength_multiplier']
        else:
            trend_multiplier = 0.7

        # 根据RSI状态调整（超买超卖区域减仓）
        rsi = price_data['technical_data'].get('rsi', 50)
        if rsi > 75 or rsi < 25:
            rsi_multiplier = 0.7
        else:
            rsi_multiplier = 1.0

        # 计算建议投入USDT金额

        multip_ratio = confidence_multiplier * trend_multiplier * rsi_multiplier

        suggested_usdt = usdt_total * multip_ratio

        max_usdt = usdt_total * config['position_ratio_max']


        strategy_usdt = min(suggested_usdt, max_usdt)

        # 计算本次应该给的仓位
        batch_usdt = usdt_used + (usdt_total * config['position_ratio_single_trade']) * multip_ratio*1.5

        final_usdt = min(strategy_usdt, batch_usdt)

        # 买入信号的时候，不要轻易减仓
        if signal_data['signal'] == 'BUY':
            if final_usdt < usdt_used:
                final_usdt = usdt_used

        else:
            final_usdt = usdt_total * config['position_ratio_single_trade']
        # 计算BTC数量

        contract_size: Any = (final_usdt * TRADE_CONFIG['leverage']) / (price_data['price'] )

        logger.info(f"仓位计算: 信心{confidence_multiplier}x 趋势{trend_multiplier}x RSI{rsi_multiplier}x -> 建议 : {suggested_usdt:.2f} USDT")
        logger.info(f"仓位计算: 本轮次： {batch_usdt:.2f} USDT, 最大允许：{max_usdt:.2f} USDT, 最终: {final_usdt:.2f} USDT")



        contract_size = round(max(contract_size, TRADE_CONFIG.get('min_amount', 0.002)), 3)

        logger.info(f"仓位最终: {contract_size} BTC")

        return contract_size

    except Exception as e:
        logger.error(f"仓位计算失败，使用基础仓位: {e}")
        return 0.002


def execute_trade(signal_data, price_data):
    """执行智能交易"""

    current_position = get_current_position()

    # 计算智能仓位
    position_size = calculate_intelligent_position(signal_data, price_data, current_position)

    logger.info(f"交易信号: {signal_data['signal']}")
    logger.info(f"信心程度: {signal_data['confidence']}")
    logger.info(f"智能仓位: {position_size} BTC")
    logger.info(f"理由: {signal_data['reason']}")
    logger.info(f"当前持仓: {current_position}")

    # 风险管理
    if signal_data['confidence'] == 'LOW' and not TRADE_CONFIG['test_mode']:
        logger.warning("低信心信号，跳过执行")
        return

    if TRADE_CONFIG['test_mode']:
        logger.info("测试模式 - 仅模拟交易")
        return

    try:
        if signal_data['signal'] == 'BUY':
            if current_position and current_position['side'] == 'short':
                logger.info(f"平空仓 {current_position['size']} 并开多仓 {position_size}...")
                exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'],
                    current_position['size'],
                    {'positionSide': 'short'}
                )
                logger.info(f"平空仓成功，数量: {current_position['size']}")
                # 开多仓
                time.sleep(2)
                exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'],
                    position_size,
                    {'positionSide': 'long'}
                )
                logger.info(f"开多仓成功，数量: {position_size}")
            elif current_position and current_position['side'] == 'long':
                size_diff = position_size - current_position['size']
                if abs(size_diff) >= 0.002:
                    if size_diff > 0:
                        logger.info(f"多仓加仓 {size_diff:.3f}...")
                        exchange.create_market_buy_order(
                            TRADE_CONFIG['symbol'],
                            round(size_diff, 3),
                            {'positionSide': 'long'}
                        )
                    else:
                        logger.info(f"多仓减仓 {abs(size_diff):.3f}...")
                        exchange.create_market_sell_order(
                            TRADE_CONFIG['symbol'],
                            round(abs(size_diff), 3),
                            {'positionSide': 'long'}
                        )
                else:
                    logger.info("已有多头持仓，仓位合适保持现状")
            else:
                logger.info(f"开多仓 {position_size}...")
                exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'],
                    position_size,
                    {'positionSide': 'long'}
                )
                logger.info(f"开多仓成功，数量: {position_size}")

        elif signal_data['signal'] == 'SELL':
            if current_position and current_position['side'] == 'long':
                logger.info("平多仓.....")
                # 先平多仓，再开空仓
                exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'],
                    current_position['size'],
                    {'positionSide': 'long'}
                )
                logger.info(f"平多仓成功，数量: {current_position['size']}")
            elif current_position and current_position['side'] == 'short':
                logger.info(f"平空仓...")
                exchange.create_market_buy_order(
                    TRADE_CONFIG['symbol'],
                    current_position['size'],
                    {'positionSide': 'short'}
                )
                logger.info(f"平空仓成功，数量: {current_position['size']}")
            else:
                logger.info(f"开空仓 {position_size}...")
                exchange.create_market_sell_order(
                    TRADE_CONFIG['symbol'],
                    position_size,
                    {'positionSide': 'short'}
                )
                logger.info(f"开空仓成功，数量: {position_size}")

        elif signal_data['signal'] == 'HOLD':
            logger.info("建议观望，不执行交易")
            return

        logger.info("智能交易执行成功")
        time.sleep(2)
        position = get_current_position()
        logger.info(f"更新后持仓: {position}")

    except ccxt.InsufficientFunds as e:
        logger.error(f"资金不足，交易失败: {e}")
    except ccxt.NetworkError as e:
        logger.error(f"网络错误，交易失败: {e}")
    except ccxt.ExchangeError as e:
        logger.error(f"交易所错误，交易失败: {e}")
    except Exception as e:
        logger.error(f"订单执行失败: {e}")
        logger.debug(traceback.format_exc())

def trading_bot():
    """主交易机器人函数"""
    logger.info("=" * 60)
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. 获取K线数据
    price_data = get_btc_ohlcv()
    if not price_data:
        logger.error("无法获取K线数据，本次交易终止")
        return

    logger.info(f"BTC当前价格: ${price_data['price']:,.2f}")
    logger.info(f"数据周期: {TRADE_CONFIG['timeframe']}")
    logger.info(f"价格变化: {price_data['price_change']:+.2f}%")

    # 2. 使用DeepSeek分析
    signal_data = analyze_with_deepseek(price_data)
    if not signal_data:
        logger.error("无法获取交易信号，本次交易终止")
        return

    # 3. 执行交易
    execute_trade(signal_data, price_data)


def main():
    """主函数"""
    logger.info("BTC/USDT 自动交易机器人启动成功！")

    if TRADE_CONFIG['test_mode']:
        logger.info("当前为模拟模式，不会真实下单")
    else:
        logger.info("实盘交易模式，请谨慎操作！")

    logger.info(f"交易周期: {TRADE_CONFIG['timeframe']}")
    logger.info("已启用K线数据分析和持仓跟踪功能")

    # 设置交易所
    if not setup_exchange():
        logger.error("交易所初始化失败，程序退出")
        return

    # 根据时间周期设置执行频率
    if TRADE_CONFIG['timeframe'] == '1h':
        # 每小时执行一次，在整点后的1分钟执行
        schedule.every().hour.at(":01").do(trading_bot)
        logger.info("执行频率: 每小时一次")
    elif TRADE_CONFIG['timeframe'] == '15m':
        # 每15分钟执行一次
        schedule.every(15).minutes.do(trading_bot)
        logger.info("执行频率: 每15分钟一次")
    else:
        # 默认1小时
        schedule.every().hour.at(":01").do(trading_bot)
        logger.info("执行频率: 每小时一次")

    # 立即执行一次
    try:
        logger.info("执行初始交易...")
        trading_bot()
    except Exception as e:
        logger.error(f"初始交易执行失败: {e}")
        logger.debug(traceback.format_exc())

    # 循环执行
    logger.info("进入定时执行循环...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("用户中断，程序退出")
    except Exception as e:
        logger.error(f"程序异常终止: {e}")
        logger.debug(traceback.format_exc())
        return

if __name__ == "__main__":
    main()