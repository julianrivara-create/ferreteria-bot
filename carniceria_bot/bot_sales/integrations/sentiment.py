#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sentiment Analysis & Visualization
Track and visualize customer sentiment trends
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """Analyze customer sentiment"""
    
    def __init__(self, config):
        """
        Initialize sentiment analyzer
        
        Args:
            config: Config instance
        """
        self.config = config
        self.provider = getattr(config, 'SENTIMENT_PROVIDER', 'textblob')
        self.alert_threshold = getattr(config, 'SENTIMENT_ALERT_THRESHOLD', -0.3)
        
        # Initialize provider
        if self.provider == 'textblob':
            try:
                from textblob import TextBlob
                self.analyzer = TextBlob
                logger.info("TextBlob sentiment analyzer initialized")
            except ImportError:
                logger.error("TextBlob not installed")
                self.analyzer = None
        else:
            self.analyzer = None
    
    def analyze_message(self, message: str) -> float:
        """
        Analyze sentiment of message
        
        Args:
            message: Message text
            
        Returns:
            Sentiment score (-1 to 1)
        """
        if not self.analyzer:
            return 0.0
        
        try:
            if self.provider == 'textblob':
                blob = self.analyzer(message)
                return blob.sentiment.polarity
            else:
                return 0.0
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return 0.0
    
    def analyze_conversation(self, messages: List[str]) -> Dict:
        """
        Analyze sentiment of entire conversation
        
        Args:
            messages: List of messages
            
        Returns:
            Sentiment analysis dict
        """
        if not messages:
            return {'avg_sentiment': 0.0, 'trend': 'neutral'}
        
        sentiments = [self.analyze_message(msg) for msg in messages]
        avg_sentiment = sum(sentiments) / len(sentiments)
        
        # Calculate trend
        if len(sentiments) >= 3:
            recent_avg = sum(sentiments[-3:]) / 3
            older_avg = sum(sentiments[:-3]) / len(sentiments[:-3]) if len(sentiments) > 3 else avg_sentiment
            
            if recent_avg > older_avg + 0.1:
                trend = 'improving'
            elif recent_avg < older_avg - 0.1:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'neutral'
        
        return {
            'avg_sentiment': avg_sentiment,
            'trend': trend,
            'sentiments': sentiments
        }


class SentimentDashboard:
    """Visualize sentiment trends"""
    
    def __init__(self, slack_connector, analyzer: SentimentAnalyzer, db, config):
        """
        Initialize sentiment dashboard
        
        Args:
            slack_connector: SlackConnector instance
            analyzer: SentimentAnalyzer instance
            db: Database instance
            config: Config instance
        """
        self.slack = slack_connector
        self.analyzer = analyzer
        self.db = db
        self.config = config
        self.sentiment_history = defaultdict(list)  # {session_id: [(timestamp, sentiment)]}
    
    def track_sentiment(self, session_id: str, message: str):
        """
        Track sentiment for message
        
        Args:
            session_id: Session ID
            message: Message text
        """
        sentiment = self.analyzer.analyze_message(message)
        
        self.sentiment_history[session_id].append({
            'timestamp': datetime.now(),
            'sentiment': sentiment,
            'message': message[:100]  # Store snippet
        })
        
        # Check for alert
        if sentiment < self.analyzer.alert_threshold:
            self._send_sentiment_alert(session_id, sentiment, message)
    
    def _send_sentiment_alert(self, session_id: str, sentiment: float, message: str):
        """Send alert for negative sentiment"""
        admin_channel = getattr(self.config, 'SLACK_ADMIN_CHANNEL', None)
        
        if not admin_channel:
            return
        
        alert = f"⚠️ *Negative Sentiment Detected*\n\n"
        alert += f"Session: {session_id}\n"
        alert += f"Sentiment: {sentiment:.2f}\n"
        alert += f"Message: _{message[:100]}_\n\n"
        alert += f"_Consider handoff to human agent_"
        
        self.slack.send_message(admin_channel, alert)
    
    def generate_sentiment_report(self, period='today') -> List[Dict]:
        """
        Generate sentiment report
        
        Args:
            period: 'today', 'week', 'month'
            
        Returns:
            List of Slack blocks
        """
        # Get sentiment data
        data = self._get_sentiment_data(period)
        
        blocks = []
        
        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"😊 Sentiment Analysis - {period.title()}"
            }
        })
        
        # Overall metrics
        avg_sentiment = data['avg_sentiment']
        trend = data['trend']
        
        sentiment_emoji = self._get_sentiment_emoji(avg_sentiment)
        trend_emoji = self._get_trend_emoji(trend)
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Avg Sentiment:*\n{sentiment_emoji} {avg_sentiment:.2f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Trend:*\n{trend_emoji} {trend.title()}"
                }
            ]
        })
        
        # Sentiment breakdown
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Sentiment Breakdown*"
            }
        })
        
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Positive:*\n{data['positive_count']} ({data['positive_pct']:.1f}%)"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Neutral:*\n{data['neutral_count']} ({data['neutral_pct']:.1f}%)"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Negative:*\n{data['negative_count']} ({data['negative_pct']:.1f}%)"
                }
            ]
        })
        
        # Alert if negative trend
        if avg_sentiment < -0.3:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ *Alert:* Negative sentiment detected. Review recent conversations."
                }
            })
        
        return blocks
    
    def _get_sentiment_data(self, period: str) -> Dict:
        """Get sentiment data for period"""
        # Get date range
        now = datetime.now()
        if period == 'today':
            start_date = now.replace(hour=0, minute=0, second=0)
        elif period == 'week':
            start_date = now - timedelta(days=7)
        else:
            start_date = now - timedelta(days=30)
        
        # Collect sentiments from history
        all_sentiments = []
        for session_id, history in self.sentiment_history.items():
            for entry in history:
                if entry['timestamp'] >= start_date:
                    all_sentiments.append(entry['sentiment'])
        
        if not all_sentiments:
            return {
                'avg_sentiment': 0.0,
                'trend': 'neutral',
                'positive_count': 0,
                'neutral_count': 0,
                'negative_count': 0,
                'positive_pct': 0,
                'neutral_pct': 0,
                'negative_pct': 0
            }
        
        # Calculate metrics
        avg_sentiment = sum(all_sentiments) / len(all_sentiments)
        
        positive_count = sum(1 for s in all_sentiments if s > 0.1)
        neutral_count = sum(1 for s in all_sentiments if -0.1 <= s <= 0.1)
        negative_count = sum(1 for s in all_sentiments if s < -0.1)
        
        total = len(all_sentiments)
        
        # Calculate trend
        if len(all_sentiments) >= 10:
            recent_avg = sum(all_sentiments[-10:]) / 10
            older_avg = sum(all_sentiments[:-10]) / len(all_sentiments[:-10])
            
            if recent_avg > older_avg + 0.1:
                trend = 'improving'
            elif recent_avg < older_avg - 0.1:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'neutral'
        
        return {
            'avg_sentiment': avg_sentiment,
            'trend': trend,
            'positive_count': positive_count,
            'neutral_count': neutral_count,
            'negative_count': negative_count,
            'positive_pct': (positive_count / total * 100) if total > 0 else 0,
            'neutral_pct': (neutral_count / total * 100) if total > 0 else 0,
            'negative_pct': (negative_count / total * 100) if total > 0 else 0
        }
    
    def _get_sentiment_emoji(self, sentiment: float) -> str:
        """Get emoji for sentiment score"""
        if sentiment > 0.5:
            return "😄"
        elif sentiment > 0.1:
            return "🙂"
        elif sentiment > -0.1:
            return "😐"
        elif sentiment > -0.5:
            return "😕"
        else:
            return "😞"
    
    def _get_trend_emoji(self, trend: str) -> str:
        """Get emoji for trend"""
        if trend == 'improving':
            return "📈"
        elif trend == 'declining':
            return "📉"
        else:
            return "➡️"
