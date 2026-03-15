"""
Sentiment Analysis — News and social media signal generation.

Sources (all FREE):
  - Financial news headlines (RSS feeds)
  - Reddit posts (via API)

Analysis:
  - Keyword-based sentiment scoring
  - Headline sentiment aggregation
  - Bullish/bearish signal generation

Usage:
    from ai.sentiment import SentimentAnalyzer
    analyzer = SentimentAnalyzer()
    score = analyzer.analyze_symbol("AAPL")
    # score: -1.0 (very bearish) to +1.0 (very bullish)
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Sentiment Lexicon ─────────────────────────────────────────────
# Financial-specific sentiment words with weights

BULLISH_WORDS = {
    # Strong bullish
    "surge": 0.9, "soar": 0.9, "skyrocket": 0.9, "moon": 0.8,
    "breakout": 0.8, "rally": 0.8, "boom": 0.8, "rocket": 0.8,
    # Moderate bullish
    "gains": 0.6, "profit": 0.6, "growth": 0.6, "bullish": 0.7,
    "upgrade": 0.7, "outperform": 0.7, "beat": 0.6, "exceed": 0.6,
    "positive": 0.5, "strong": 0.5, "rise": 0.5, "jump": 0.6,
    "buy": 0.5, "accumulate": 0.5, "undervalued": 0.6,
    # Mild bullish
    "up": 0.3, "higher": 0.3, "increase": 0.3, "recover": 0.4,
    "improve": 0.3, "optimistic": 0.4, "confidence": 0.3,
}

BEARISH_WORDS = {
    # Strong bearish
    "crash": -0.9, "plunge": -0.9, "collapse": -0.9, "tank": -0.8,
    "bankrupt": -0.9, "fraud": -0.9, "scandal": -0.8, "crisis": -0.8,
    # Moderate bearish
    "loss": -0.6, "decline": -0.6, "bearish": -0.7, "downgrade": -0.7,
    "underperform": -0.7, "miss": -0.6, "fail": -0.6, "weak": -0.5,
    "sell": -0.5, "overvalued": -0.6, "bubble": -0.6, "recession": -0.7,
    # Mild bearish
    "down": -0.3, "lower": -0.3, "decrease": -0.3, "concern": -0.4,
    "risk": -0.3, "warning": -0.4, "uncertainty": -0.4, "volatile": -0.3,
    "fear": -0.5, "worry": -0.4, "cut": -0.3, "layoff": -0.5,
}

ALL_SENTIMENT = {**BULLISH_WORDS, **BEARISH_WORDS}


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    symbol: str
    score: float          # -1.0 to +1.0
    label: str            # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float     # 0.0 to 1.0
    headlines_analyzed: int
    top_bullish: List[str]
    top_bearish: List[str]
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def is_bullish(self) -> bool:
        return self.score > 0.15

    @property
    def is_bearish(self) -> bool:
        return self.score < -0.15


class SentimentAnalyzer:
    """
    Analyzes news sentiment for trading signals.

    Uses free data sources (RSS feeds) and a financial-specific
    sentiment lexicon for scoring.
    """

    # Free financial news RSS feeds
    RSS_FEEDS = {
        "yahoo_finance": "https://finance.yahoo.com/rss/headline?s={symbol}",
        "google_news": "https://news.google.com/rss/search?q={symbol}+stock",
        "seeking_alpha": "https://seekingalpha.com/api/sa/combined/{symbol}.xml",
        "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    }

    def __init__(self, cache_duration_minutes: int = 30):
        self._cache: Dict[str, SentimentResult] = {}
        self._cache_duration = timedelta(minutes=cache_duration_minutes)

    def analyze_symbol(self, symbol: str, force_refresh: bool = False) -> SentimentResult:
        """
        Analyze sentiment for a single symbol.

        Args:
            symbol: Stock/crypto ticker
            force_refresh: Bypass cache

        Returns:
            SentimentResult with score, label, and details
        """
        # Check cache
        if not force_refresh and symbol in self._cache:
            cached = self._cache[symbol]
            if datetime.now() - cached.timestamp < self._cache_duration:
                return cached

        # Fetch headlines
        headlines = self._fetch_headlines(symbol)

        if not headlines:
            return SentimentResult(
                symbol=symbol, score=0.0, label="NEUTRAL",
                confidence=0.0, headlines_analyzed=0,
                top_bullish=[], top_bearish=[],
            )

        # Analyze
        result = self._score_headlines(symbol, headlines)

        # Cache
        self._cache[symbol] = result

        return result

    def analyze_multiple(self, symbols: List[str]) -> Dict[str, SentimentResult]:
        """Analyze sentiment for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.analyze_symbol(symbol)
            except Exception as e:
                logger.error(f"Sentiment analysis failed for {symbol}: {e}")
                results[symbol] = SentimentResult(
                    symbol=symbol, score=0.0, label="NEUTRAL",
                    confidence=0.0, headlines_analyzed=0,
                    top_bullish=[], top_bearish=[],
                )
        return results

    def telegram_report(self, symbols: List[str]) -> str:
        """Generate a Telegram-formatted sentiment report."""
        results = self.analyze_multiple(symbols)

        lines = ["📰 *Market Sentiment*\n"]
        for symbol, r in results.items():
            if r.is_bullish:
                emoji = "🟢"
            elif r.is_bearish:
                emoji = "🔴"
            else:
                emoji = "⚪"

            lines.append(
                f"{emoji} *{symbol}*: {r.label} ({r.score:+.2f})\n"
                f"   📊 {r.headlines_analyzed} headlines analyzed"
            )

        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────

    def _fetch_headlines(self, symbol: str) -> List[str]:
        """Fetch news headlines for a symbol from RSS feeds."""
        headlines = []

        try:
            import requests

            # Yahoo Finance RSS
            url = self.RSS_FEEDS["yahoo_finance"].format(symbol=symbol)
            try:
                resp = requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (QuantumTrade Bot)"
                })
                if resp.status_code == 200:
                    # Simple XML parsing without lxml dependency
                    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
                    if not titles:
                        titles = re.findall(r"<title>(.*?)</title>", resp.text)
                    headlines.extend(titles[:15])
            except Exception as e:
                logger.debug(f"Yahoo RSS failed: {e}")

            # Google News RSS
            url = self.RSS_FEEDS["google_news"].format(symbol=symbol)
            try:
                resp = requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 (QuantumTrade Bot)"
                })
                if resp.status_code == 200:
                    titles = re.findall(r"<title>(.*?)</title>", resp.text)
                    headlines.extend(titles[:15])
            except Exception as e:
                logger.debug(f"Google News RSS failed: {e}")

        except ImportError:
            logger.warning("requests not installed for sentiment analysis")

        # Deduplicate
        seen = set()
        unique = []
        for h in headlines:
            clean = h.strip().lower()
            if clean and clean not in seen and len(clean) > 10:
                seen.add(clean)
                unique.append(h.strip())

        logger.debug(f"Fetched {len(unique)} headlines for {symbol}")
        return unique

    def _score_headlines(self, symbol: str, headlines: List[str]) -> SentimentResult:
        """Score a list of headlines for sentiment."""
        scores = []
        bullish_headlines = []
        bearish_headlines = []

        for headline in headlines:
            score = self._score_text(headline)
            scores.append(score)

            if score > 0.2:
                bullish_headlines.append(headline[:80])
            elif score < -0.2:
                bearish_headlines.append(headline[:80])

        # Aggregate score (mean of all headline scores)
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Clip to [-1, 1]
        avg_score = max(-1.0, min(1.0, avg_score))

        # Determine label
        if avg_score > 0.15:
            label = "BULLISH"
        elif avg_score < -0.15:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        # Confidence based on agreement
        if scores:
            same_direction = sum(1 for s in scores if (s > 0) == (avg_score > 0))
            confidence = same_direction / len(scores)
        else:
            confidence = 0.0

        return SentimentResult(
            symbol=symbol,
            score=avg_score,
            label=label,
            confidence=confidence,
            headlines_analyzed=len(headlines),
            top_bullish=bullish_headlines[:3],
            top_bearish=bearish_headlines[:3],
        )

    @staticmethod
    def _score_text(text: str) -> float:
        """Score a single text string for sentiment."""
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        if not words:
            return 0.0

        total_score = 0.0
        matching_words = 0

        for word in words:
            if word in ALL_SENTIMENT:
                total_score += ALL_SENTIMENT[word]
                matching_words += 1

        if matching_words == 0:
            return 0.0

        # Normalize by sqrt of matching words to prevent
        # long texts from having outsized scores
        return total_score / (matching_words ** 0.5)
