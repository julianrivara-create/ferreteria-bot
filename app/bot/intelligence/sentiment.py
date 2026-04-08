import logging
from typing import Tuple, Dict
import re

class SentimentAnalyzer:
    """
    Análisis de sentimiento simple basado en keywords
    Para producción considerar: VADER, TextBlob, o Hugging Face
    """
    
    def __init__(self):
        # Keywords por sentimiento
        self.positive_keywords = [
            'excelente', 'perfecto', 'genial', 'buenísimo', 'gracias',
            'me encanta', 'increíble', 'maravilloso', 'feliz', 'contento',
            'bien', 'bueno', 'ok', 'dale', 'sí', 'si', 'copado', 'joya',
            'bárbaro', 'groso', 'top', '👍', '❤️', '😊', '🎉', '✅'
        ]
        
        self.negative_keywords = [
            'malo', 'pésimo', 'terrible', 'horrible', 'caro', 'no sirve',
            'fraude', 'estafa', 'robo', 'decepción', 'mala', 'peor',
            'nunca', 'jamás', 'nada', 'basura', 'porquería', 'chatarra',
            'furioso', 'enojado', 'molesto', 'frustrado', 'harto',
            '😡', '😤', '👎', '❌'
        ]
        
        self.frustration_keywords = [
            'no entiendo', 'no funciona', 'error', 'problema', 'ayuda',
            'no puedo', 'no me deja', 'stuck', 'bloqueado', 'confundido',
            'complicado', 'difícil'
        ]
        
        self.hesitation_keywords = [
            'no sé', 'pensarlo', 'dudas', 'tal vez', 'quizás',
            'no estoy seguro', 'después', 'luego', 'mañana'
        ]
    
    def analyze(self, text: str) -> Tuple[str, float, Dict]:
        """
        Analiza sentimiento del texto
        
        Returns:
            (sentiment, confidence, details)
            sentiment: 'positive', 'negative', 'neutral', 'frustrated', 'hesitant'
            confidence: 0.0-1.0
            details: {
                'score': int (-10 to +10),
                'positive_count': int,
                'negative_count': int,
                'keywords_found': []
            }
        """
        text_lower = text.lower()
        
        # Contadores
        positive_count = sum(1 for kw in self.positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in self.negative_keywords if kw in text_lower)
        frustration_count = sum(1 for kw in self.frustration_keywords if kw in text_lower)
        hesitation_count = sum(1 for kw in self.hesitation_keywords if kw in text_lower)
        
        keywords_found = []
        
        # Score (-10 a +10)
        score = positive_count - negative_count
        
        # Determinar sentimiento principal
        if frustration_count >= 2:
            sentiment = 'frustrated'
            confidence = min(frustration_count / 3, 1.0)
            keywords_found = [kw for kw in self.frustration_keywords if kw in text_lower]
        
        elif hesitation_count >= 2:
            sentiment = 'hesitant'
            confidence = min(hesitation_count / 3, 1.0)
            keywords_found = [kw for kw in self.hesitation_keywords if kw in text_lower]
        
        elif score > 2:
            sentiment = 'positive'
            confidence = min(score / 5, 1.0)
            keywords_found = [kw for kw in self.positive_keywords if kw in text_lower]
        
        elif score < -2:
            sentiment = 'negative'
            confidence = min(abs(score) / 5, 1.0)
            keywords_found = [kw for kw in self.negative_keywords if kw in text_lower]
        
        else:
            sentiment = 'neutral'
            confidence = 0.5
        
        details = {
            'score': score,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'frustration_count': frustration_count,
            'hesitation_count': hesitation_count,
            'keywords_found': keywords_found[:5]  # Top 5
        }
        
        return sentiment, confidence, details
    
    def should_escalate(self, sentiment: str, confidence: float) -> bool:
        """
        Determina si debe escalar a humano
        
        Returns:
            True si sentimiento negativo fuerte o frustración
        """
        if sentiment == 'negative' and confidence > 0.7:
            return True
        
        if sentiment == 'frustrated' and confidence > 0.6:
            return True
        
        return False
    
    def get_response_tone(self, sentiment: str) -> str:
        """
        Sugiere tono de respuesta basado en sentimiento
        
        Returns:
            Sugerencia de tono para el bot
        """
        tone_map = {
            'positive': 'enthusiastic',  # Entusiasta, igualmente positivo
            'negative': 'empathetic',    # Empático, disculparse
            'frustrated': 'helpful',     # Muy servicial, ofrecer ayuda
            'hesitant': 'reassuring',    # Tranquilizador, dar confianza
            'neutral': 'friendly'        # Amigable estándar
        }
        
        return tone_map.get(sentiment, 'friendly')
