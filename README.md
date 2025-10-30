# BTC/USDT Automated Trading Bot

An intelligent cryptocurrency trading bot powered by DeepSeek AI for Binance futures trading, featuring advanced technical analysis, sentiment indicators, and adaptive position management.

## Features

### 🤖 AI-Powered Trading Signals
- **DeepSeek AI Integration**: Advanced market analysis using DeepSeek's language model
- **Multi-factor Analysis**: Combines technical indicators, market sentiment, and trend analysis
- **Confidence-based Signals**: HIGH/MEDIUM/LOW confidence levels for risk management

### 📊 Technical Analysis
- **Moving Averages**: SMA 5/20/50 for multi-timeframe trend analysis
- **MACD**: Exponential Moving Average Convergence Divergence
- **RSI**: Relative Strength Index for momentum analysis
- **Bollinger Bands**: Dynamic support and resistance levels
- **Volume Analysis**: Volume ratio and moving averages
- **Support/Resistance**: Automatic detection of key price levels

### 💡 Market Sentiment Analysis
- **CryptoOracle Integration**: Real-time market sentiment data
- **Sentiment Weighting**: 30% weight in trading decisions
- **Multi-source Validation**: Combines positive/negative sentiment ratios

### 🎯 Intelligent Position Management
- **Dynamic Position Sizing**: Adjusts position size based on:
  - Signal confidence level (HIGH: 1.5x, MEDIUM: 1.0x, LOW: 0.5x)
  - Trend strength (Strong trends: 1.2x multiplier)
  - RSI extremes (Reduces size in overbought/oversold conditions)
- **Risk Controls**: Maximum position ratio and minimum trade size limits
- **Position Adjustment**: Smart add/reduce positions based on market conditions

### 🛡️ Risk Management
- **Anti-Frequent Trading**: Prevents excessive position changes
- **Trend Confirmation**: Requires 2-3 indicator confirmations for reversal signals
- **Low Confidence Filter**: Skips execution of low-confidence signals in live mode
- **Stop Loss & Take Profit**: AI-generated price targets based on technical analysis

### 📝 Comprehensive Logging
- **Daily Log Files**: Organized in `logs/` directory with date stamps
- **Dual Output**: Console and file logging for easy monitoring
- **Debug Mode**: Detailed request/response logging for troubleshooting

## Installation

### Prerequisites
- Python 3.8+
- Binance account with futures trading enabled
- DeepSeek API key

### Setup

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd trade_ds
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create a `.env` file in the project root:

```env
# DeepSeek API
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Binance API (for deepseek.py)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET=your_binance_secret


## Configuration

### Trading Parameters (`TRADE_CONFIG`)

```python
TRADE_CONFIG = {
    'symbol': 'BTC/USDT',           # Trading pair
    'leverage': 10,                  # Leverage multiplier
    'timeframe': '15m',              # Candlestick timeframe
    'test_mode': False,              # Enable/disable paper trading
    'data_points': 96,               # Historical data points (24h for 15m)
    
    # Position Management
    'position_management': {
        'enable_intelligent_position': True,
        'base_usdt_amount': 100,              # Base position size in USDT
        'high_confidence_multiplier': 1.5,
        'medium_confidence_multiplier': 1.0,
        'low_confidence_multiplier': 0.5,
        'max_position_ratio': 0.1,            # Max 10% of balance per trade
        'trend_strength_multiplier': 1.2
    }
}
```

## Usage

### Binance Futures Trading

```bash
python deepseek.py
```

### OKX Futures Trading

```bash
python deepseek_okx.py
```

### Test Mode (Paper Trading)

Set `test_mode: True` in the config to simulate trading without real orders:

```python
TRADE_CONFIG = {
    'test_mode': True,
    # ... other configs
}
```

## How It Works

### 1. Data Collection (Every 15 minutes)
- Fetches 96 candlesticks (24 hours of 15m data)
- Calculates technical indicators
- Retrieves market sentiment data
- Checks current positions

### 2. AI Analysis
The bot sends comprehensive market data to DeepSeek AI:
- Recent K-line patterns
- Technical indicator values
- Trend analysis summary
- Market sentiment scores
- Current position status

### 3. Signal Generation
DeepSeek AI returns:
- **Signal**: BUY / SELL / HOLD
- **Reason**: Detailed analysis explanation
- **Stop Loss**: Recommended stop loss price
- **Take Profit**: Recommended take profit price
- **Confidence**: HIGH / MEDIUM / LOW

### 4. Position Execution
- **Intelligent Sizing**: Calculates optimal position based on confidence and market conditions
- **Smart Adjustments**: Adds to winning positions, reduces losing ones
- **Reversal Protection**: Requires high confidence for direction changes
- **Cost Awareness**: Minimizes unnecessary trades

## Trading Logic

### Signal Priority
1. **Technical Analysis** (60% weight)
   - Trend direction (SMA alignment)
   - RSI momentum
   - MACD crossovers
   - Bollinger Band position

2. **Market Sentiment** (30% weight)
   - Positive/negative sentiment ratio
   - Net sentiment score
   - Used for signal confirmation

3. **Risk Management** (10% weight)
   - Current position PnL
   - Account balance
   - Position limits

### Anti-Frequent Trading Rules
- Trend continuity prioritized over short-term noise
- Position stability unless strong reversal confirmed
- Minimum 2-3 indicator confirmations for reversals
- Transaction cost awareness

## File Structure

```
trade_ds/
├── deepseek.py              # Binance futures trading bot
├── deepseek_okx.py          # OKX futures trading bot
├── requirements.txt         # Python dependencies
├── .env                     # API keys and secrets (create this)
├── logs/                    # Daily log files (auto-created)
│   └── trading_YYYYMMDD.log
└── README.md               # This file
```

## Dependencies

- `ccxt`: Cryptocurrency exchange integration
- `openai`: DeepSeek API client
- `pandas`: Data analysis and manipulation
- `schedule`: Task scheduling
- `python-dotenv`: Environment variable management
- `requests`: HTTP requests for sentiment API

## Risk Warnings

⚠️ **IMPORTANT DISCLAIMERS**

1. **Financial Risk**: Cryptocurrency trading involves substantial risk of loss. Never invest more than you can afford to lose.

2. **Leverage Risk**: This bot uses leverage (default 10x), which amplifies both gains and losses.

3. **AI Limitations**: DeepSeek AI predictions are not guaranteed. Market conditions can change rapidly.

4. **Testing Required**: Always test thoroughly in `test_mode` before live trading.

5. **API Security**: Keep your API keys secure. Use API key restrictions (IP whitelist, trading-only permissions).

6. **Market Volatility**: Crypto markets are highly volatile. Monitor your bot regularly.

7. **No Guarantees**: Past performance does not guarantee future results.

## Best Practices

### Before Going Live
1. ✅ Test extensively in `test_mode: True`
2. ✅ Start with small `base_usdt_amount` (e.g., $10-$50)
3. ✅ Use exchange API restrictions (IP whitelist, no withdrawals)
4. ✅ Monitor the first 24 hours closely
5. ✅ Set appropriate `max_position_ratio` (recommend 0.05-0.10)

### Ongoing Monitoring
- Check daily log files in `logs/` directory
- Monitor exchange account balance
- Review signal history and confidence levels
- Adjust position sizing based on performance

### Safety Features
- Low confidence signals are skipped in live mode
- Maximum position ratio prevents over-exposure
- Trend confirmation reduces false signals
- Comprehensive error handling and logging

## Troubleshooting

### Common Issues

**Bot doesn't execute trades**
- Check `test_mode` setting
- Verify API keys in `.env`
- Check exchange account balance
- Review log files for errors

**"Insufficient Funds" error**
- Increase account balance
- Reduce `base_usdt_amount`
- Check available margin

**API connection errors**
- Verify API key permissions
- Check IP whitelist settings
- Ensure stable internet connection

**Signal always HOLD**
- Market may be in consolidation
- Check technical indicator values in logs
- Try different timeframe

## Advanced Configuration

### Custom Timeframes
Supported timeframes: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`

```python
'timeframe': '15m',  # Change to your preferred timeframe
'data_points': 96,   # Adjust accordingly (e.g., 24 for 1h = 24h data)
```

### Position Management Tuning
```python
'position_management': {
    'enable_intelligent_position': True,     # Set False for fixed size
    'base_usdt_amount': 100,                 # Adjust based on capital
    'max_position_ratio': 0.1,               # Lower = more conservative
}
```

## Performance Metrics

The bot logs:
- Signal statistics (BUY/SELL/HOLD distribution)
- Consecutive signal warnings
- Position changes and PnL
- Technical indicator values
- Market sentiment scores

## Support & Contribution

For issues, questions, or contributions, please refer to the project repository.

## License

[Specify your license here]

---

**Disclaimer**: This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred.
