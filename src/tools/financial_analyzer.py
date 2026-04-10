from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
import pandas as pd
from dataclasses import dataclass

from src.state import AnalysisResult


@dataclass
class TechnicalIndicators:
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    rsi: float
    macd: float
    macd_signal: float
    macd_hist: float
    bollinger_upper: float
    bollinger_middle: float
    bollinger_lower: float


class FinancialAnalyzer:
    def __init__(self):
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bollinger_period = 20
        self.bollinger_std = 2
    
    def calculate_ma(self, prices: List[float], period: int) -> float:
        if len(prices) < period:
            return 0.0
        return float(np.mean(prices[-period:]))
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        if len(prices) < period:
            return 0.0
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def calculate_macd(self, prices: List[float]) -> tuple:
        if len(prices) < self.macd_slow + self.macd_signal:
            return 0.0, 0.0, 0.0
        
        ema_fast = self.calculate_ema(prices, self.macd_fast)
        ema_slow = self.calculate_ema(prices, self.macd_slow)
        
        macd_line = ema_fast - ema_slow
        
        macd_values = []
        for i in range(self.macd_slow, len(prices)):
            ema_f = self.calculate_ema(prices[:i+1], self.macd_fast)
            ema_s = self.calculate_ema(prices[:i+1], self.macd_slow)
            macd_values.append(ema_f - ema_s)
        
        signal_line = self.calculate_ema(macd_values, self.macd_signal) if len(macd_values) >= self.macd_signal else 0.0
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def calculate_bollinger(self, prices: List[float]) -> tuple:
        if len(prices) < self.bollinger_period:
            return 0.0, 0.0, 0.0
        
        recent_prices = prices[-self.bollinger_period:]
        middle = np.mean(recent_prices)
        std = np.std(recent_prices)
        
        upper = middle + self.bollinger_std * std
        lower = middle - self.bollinger_std * std
        
        return upper, middle, lower
    
    def calculate_technical_indicators(self, prices: List[float]) -> TechnicalIndicators:
        ma5 = self.calculate_ma(prices, 5)
        ma10 = self.calculate_ma(prices, 10)
        ma20 = self.calculate_ma(prices, 20)
        ma60 = self.calculate_ma(prices, 60)
        
        rsi = self.calculate_rsi(prices)
        
        macd, signal, hist = self.calculate_macd(prices)
        
        boll_upper, boll_middle, boll_lower = self.calculate_bollinger(prices)
        
        return TechnicalIndicators(
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            rsi=rsi,
            macd=macd,
            macd_signal=signal,
            macd_hist=hist,
            bollinger_upper=boll_upper,
            bollinger_middle=boll_middle,
            bollinger_lower=boll_lower
        )
    
    def analyze_trend(self, prices: List[float]) -> Dict[str, Any]:
        if len(prices) < 20:
            return {"trend": "数据不足", "confidence": 0.0}
        
        indicators = self.calculate_technical_indicators(prices)
        current_price = prices[-1]
        
        signals = []
        
        if current_price > indicators.ma5 > indicators.ma10 > indicators.ma20:
            signals.append(("多头排列", 1))
        elif current_price < indicators.ma5 < indicators.ma10 < indicators.ma20:
            signals.append(("空头排列", -1))
        
        if indicators.rsi > 70:
            signals.append(("超买", -0.5))
        elif indicators.rsi < 30:
            signals.append(("超卖", 0.5))
        
        if indicators.macd > indicators.macd_signal and indicators.macd_hist > 0:
            signals.append(("MACD金叉", 1))
        elif indicators.macd < indicators.macd_signal and indicators.macd_hist < 0:
            signals.append(("MACD死叉", -1))
        
        if current_price > indicators.bollinger_upper:
            signals.append(("突破布林上轨", -0.5))
        elif current_price < indicators.bollinger_lower:
            signals.append(("跌破布林下轨", 0.5))
        
        total_score = sum(s[1] for s in signals)
        
        if total_score > 1:
            trend = "上涨趋势"
        elif total_score < -1:
            trend = "下跌趋势"
        else:
            trend = "震荡趋势"
        
        confidence = min(abs(total_score) / 3, 1.0)
        
        return {
            "trend": trend,
            "confidence": confidence,
            "signals": [s[0] for s in signals],
            "indicators": {
                "MA5": round(indicators.ma5, 2),
                "MA10": round(indicators.ma10, 2),
                "MA20": round(indicators.ma20, 2),
                "RSI": round(indicators.rsi, 2),
                "MACD": round(indicators.macd, 4),
                "MACD_Signal": round(indicators.macd_signal, 4),
                "Bollinger_Upper": round(indicators.bollinger_upper, 2),
                "Bollinger_Lower": round(indicators.bollinger_lower, 2),
            }
        }
    
    def calculate_volatility(self, prices: List[float], period: int = 20) -> Dict[str, float]:
        if len(prices) < period:
            return {"volatility": 0.0, "annualized_volatility": 0.0}
        
        returns = np.diff(np.log(prices[-period:]))
        volatility = np.std(returns)
        annualized_volatility = volatility * np.sqrt(252)
        
        return {
            "volatility": round(volatility, 4),
            "annualized_volatility": round(annualized_volatility, 4)
        }
    
    def calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.03) -> float:
        if len(returns) < 2:
            return 0.0
        
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        sharpe = (avg_return - risk_free_rate / 252) / std_return
        return round(sharpe * np.sqrt(252), 4)
    
    def calculate_max_drawdown(self, prices: List[float]) -> Dict[str, float]:
        if len(prices) < 2:
            return {"max_drawdown": 0.0, "drawdown_duration": 0}
        
        peak = prices[0]
        max_dd = 0.0
        dd_start = 0
        dd_duration = 0
        
        for i, price in enumerate(prices):
            if price > peak:
                peak = price
                dd_start = i
            
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd
                dd_duration = i - dd_start
        
        return {
            "max_drawdown": round(max_dd, 4),
            "drawdown_duration": dd_duration
        }
    
    def calculate_financial_ratios(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        ratios = {}
        
        try:
            if "income_statement" in financial_data and financial_data["income_statement"]:
                income = financial_data["income_statement"][0]
                
                revenue = income.get("营业收入", 0)
                net_profit = income.get("净利润", 0)
                
                if revenue and revenue != 0:
                    ratios["net_profit_margin"] = round(net_profit / revenue, 4)
        except:
            pass
        
        try:
            if "balance_sheet" in financial_data and financial_data["balance_sheet"]:
                balance = financial_data["balance_sheet"][0]
                
                total_assets = balance.get("资产总计", 0)
                total_liabilities = balance.get("负债合计", 0)
                owner_equity = balance.get("所有者权益合计", 0)
                
                if total_assets and total_assets != 0:
                    ratios["debt_ratio"] = round(total_liabilities / total_assets, 4)
                
                if owner_equity and owner_equity != 0:
                    ratios["equity_multiplier"] = round(total_assets / owner_equity, 4)
        except:
            pass
        
        return ratios
    
    def generate_analysis_result(self, indicator_name: str, value: float, 
                                  description: str) -> AnalysisResult:
        return AnalysisResult(
            indicator_name=indicator_name,
            value=value,
            description=description,
            timestamp=datetime.now().isoformat()
        )
    
    def comprehensive_analysis(self, stock_data: Dict[str, Any]) -> List[AnalysisResult]:
        results = []
        
        if "history" in stock_data and stock_data["history"]:
            prices = [h["close"] for h in stock_data["history"]]
            
            trend_analysis = self.analyze_trend(prices)
            results.append(self.generate_analysis_result(
                "趋势分析",
                trend_analysis["confidence"],
                f"当前趋势: {trend_analysis['trend']}, 信号: {', '.join(trend_analysis['signals'])}"
            ))
            
            volatility = self.calculate_volatility(prices)
            results.append(self.generate_analysis_result(
                "波动率",
                volatility["annualized_volatility"],
                f"年化波动率: {volatility['annualized_volatility']*100:.2f}%"
            ))
            
            drawdown = self.calculate_max_drawdown(prices)
            results.append(self.generate_analysis_result(
                "最大回撤",
                drawdown["max_drawdown"],
                f"最大回撤: {drawdown['max_drawdown']*100:.2f}%"
            ))
        
        if "financial" in stock_data and stock_data["financial"]:
            financial_ratios = self.calculate_financial_ratios(
                stock_data["financial"].get("financial_data", {})
            )
            
            for ratio_name, value in financial_ratios.items():
                results.append(self.generate_analysis_result(
                    ratio_name,
                    value,
                    f"{ratio_name}: {value:.4f}"
                ))
        
        return results
    
    def comprehensive_analysis_wrapper(self, symbol: str) -> Dict[str, Any]:
        from src.tools.fallback_data_collector import fallback_data_collector
        
        history = fallback_data_collector.get_stock_history(symbol, 60)
        
        if not history or (isinstance(history, list) and len(history) > 0 and "error" in history[0]):
            return {
                "symbol": symbol,
                "error": "无法获取股票历史数据，数据源不可用"
            }
        
        prices = [h["close"] for h in history if isinstance(h, dict) and "close" in h]
        
        if not prices:
            return {
                "symbol": symbol,
                "error": "历史数据中没有有效的收盘价"
            }
        
        stock_data = {
            "history": history,
            "prices": prices
        }
        
        results = self.comprehensive_analysis(stock_data)
        
        return {
            "symbol": symbol,
            "analysis": [
                {
                    "indicator": r["indicator_name"] if isinstance(r, dict) else getattr(r, 'indicator_name', str(r)),
                    "value": r["value"] if isinstance(r, dict) else getattr(r, 'value', 0),
                    "description": r["description"] if isinstance(r, dict) else getattr(r, 'description', '')
                }
                for r in results
            ]
        }


financial_analyzer = FinancialAnalyzer()
