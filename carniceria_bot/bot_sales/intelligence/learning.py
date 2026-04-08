"""
Bot Learning System - Feedback Collection & Analytics
Sistema para recoger feedback y mejorar el bot automáticamente
"""
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class FeedbackCollector:
    """
    Sistema de recolección de feedback de conversaciones
    """
    
    def __init__(self, db_path: str = 'iphone_store.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Crea tabla de feedback"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_id TEXT,
                user_message TEXT,
                bot_response TEXT,
                rating INTEGER,
                feedback_type TEXT,
                comment TEXT,
                context TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT 0
            )
        """)
        
        # Índices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_rating 
            ON feedback(rating)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_type 
            ON feedback(feedback_type)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Feedback collector initialized")
    
    def collect_feedback(self, session_id: str, rating: int, 
                        user_message: str = None, bot_response: str = None,
                        feedback_type: str = 'rating', comment: str = None,
                        context: Dict = None) -> int:
        """
        Recolecta feedback de usuario
        
        Args:
            session_id: ID de sesión
            rating: 1-5 (thumbs down = 1-2, neutral = 3, thumbs up = 4-5)
            user_message: Mensaje del usuario
            bot_response: Respuesta del bot
            feedback_type: 'rating', 'bug', 'suggestion', 'negative'
            comment: Comentario opcional
            context: Contexto adicional (JSON)
        
        Returns:
            ID del feedback
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO feedback 
            (session_id, user_message, bot_response, rating, feedback_type, 
             comment, context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            user_message,
            bot_response,
            rating,
            feedback_type,
            comment,
            json.dumps(context) if context else None
        ))
        
        feedback_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Feedback collected: {feedback_id} (rating: {rating})")
        
        return feedback_id
    
    def get_negative_feedback(self, limit: int = 50) -> List[Dict]:
        """Obtiene feedback negativo para análisis"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM feedback
            WHERE rating <= 2 AND resolved = 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return results
    
    def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Obtiene estadísticas de feedback"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        since = datetime.now() - timedelta(days=days)
        
        # Total feedback
        cursor.execute("""
            SELECT COUNT(*) as total FROM feedback
            WHERE timestamp >= ?
        """, (since,))
        total = cursor.fetchone()['total']
        
        # Por rating
        cursor.execute("""
            SELECT rating, COUNT(*) as count
            FROM feedback
            WHERE timestamp >= ?
            GROUP BY rating
            ORDER BY rating
        """, (since,))
        by_rating = {row['rating']: row['count'] for row in cursor.fetchall()}
        
        # Por tipo
        cursor.execute("""
            SELECT feedback_type, COUNT(*) as count
            FROM feedback
            WHERE timestamp >= ?
            GROUP BY feedback_type
        """, (since,))
        by_type = {row['feedback_type']: row['count'] for row in cursor.fetchall()}
        
        # Promedio
        cursor.execute("""
            SELECT AVG(rating) as avg_rating
            FROM feedback
            WHERE timestamp >= ?
        """, (since,))
        avg_rating = cursor.fetchone()['avg_rating'] or 0
        
        # Satisfaction rate (4-5 stars)
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN rating >= 4 THEN 1 END) * 100.0 / COUNT(*) as satisfaction
            FROM feedback
            WHERE timestamp >= ?
        """, (since,))
        satisfaction = cursor.fetchone()['satisfaction'] or 0
        
        conn.close()
        
        return {
            'total_feedback': total,
            'avg_rating': round(avg_rating, 2),
            'satisfaction_rate': round(satisfaction, 1),
            'by_rating': by_rating,
            'by_type': by_type,
            'period_days': days
        }
    
    def mark_resolved(self, feedback_id: int):
        """Marca feedback como resuelto"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE feedback
            SET resolved = 1
            WHERE id = ?
        """, (feedback_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Feedback {feedback_id} marked as resolved")


class LearningAnalytics:
    """
    Analytics para identificar patrones y áreas de mejora
    """
    
    def __init__(self, db_path: str = 'iphone_store.db'):
        self.db_path = db_path
    
    def analyze_failure_patterns(self) -> List[Dict]:
        """
        Analiza patrones en respuestas mal calificadas
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Mensajes con rating bajo
        cursor.execute("""
            SELECT 
                user_message,
                bot_response,
                COUNT(*) as occurrences,
                AVG(rating) as avg_rating,
                GROUP_CONCAT(comment, ' | ') as comments
            FROM feedback
            WHERE rating <= 2
            GROUP BY user_message
            HAVING COUNT(*) >= 2
            ORDER BY occurrences DESC
            LIMIT 20
        """)
        
        patterns = []
        for row in cursor.fetchall():
            patterns.append({
                'user_message': row['user_message'],
                'bot_response': row['bot_response'],
                'occurrences': row['occurrences'],
                'avg_rating': round(row['avg_rating'], 2),
                'sample_comments': row['comments']
            })
        
        conn.close()
        
        return patterns
    
    def get_improvement_suggestions(self) -> List[str]:
        """
        Genera sugerencias de mejora basadas en feedback
        """
        patterns = self.analyze_failure_patterns()
        suggestions = []
        
        for pattern in patterns[:5]:  # Top 5
            msg = pattern['user_message']
            occurrences = pattern['occurrences']
            
            suggestion = f"Mejorar respuesta para: '{msg}' ({occurrences} casos negativos)"
            suggestions.append(suggestion)
        
        return suggestions
    
    def export_training_data(self, output_file: str = 'training_data.jsonl',
                            min_rating: int = 4):
        """
        Exporta conversaciones bien calificadas para fine-tuning
        
        Args:
            output_file: Archivo JSONL de salida
            min_rating: Rating mínimo a incluir
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_message, bot_response, rating
            FROM feedback
            WHERE rating >= ? AND user_message IS NOT NULL
        """, (min_rating,))
        
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for row in cursor.fetchall():
                # Formato OpenAI fine-tuning
                entry = {
                    "messages": [
                        {"role": "user", "content": row['user_message']},
                        {"role": "assistant", "content": row['bot_response']}
                    ]
                }
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                count += 1
        
        conn.close()
        
        logger.info(f"Exported {count} training examples to {output_file}")
        return count


class AutoImprover:
    """
    Sistema de auto-mejora del bot
    Combina feedback + A/B testing
    """
    
    def __init__(self, db_path: str = 'iphone_store.db'):
        self.db_path = db_path
        self.feedback = FeedbackCollector(db_path)
        self.analytics = LearningAnalytics(db_path)
    
    def run_improvement_cycle(self):
        """
        Ciclo de mejora automática:
        1. Analizar feedback negativo
        2. Identificar patrones
        3. Generar sugerencias
        4. (Manual) Implementar cambios
        5. A/B test
        """
        logger.info("=" * 60)
        logger.info("IMPROVEMENT CYCLE")
        logger.info("=" * 60)
        
        # Stats generales
        stats = self.feedback.get_feedback_stats(days=30)
        logger.info(f"Satisfaction: {stats['satisfaction_rate']}%")
        logger.info(f"Avg Rating: {stats['avg_rating']}/5")
        
        # Patrones de fallo
        patterns = self.analytics.analyze_failure_patterns()
        if patterns:
            logger.info(f"\nFound {len(patterns)} failure patterns:")
            for i, p in enumerate(patterns[:3], 1):
                logger.info(f"{i}. '{p['user_message']}' ({p['occurrences']} casos)")
        
        # Sugerencias
        suggestions = self.analytics.get_improvement_suggestions()
        if suggestions:
            logger.info("\nSuggested improvements:")
            for i, s in enumerate(suggestions, 1):
                logger.info(f"{i}. {s}")
        
        # Export training data
        count = self.analytics.export_training_data()
        logger.info(f"\nExported {count} examples for fine-tuning")
        
        logger.info("=" * 60)
        
        return {
            'stats': stats,
            'patterns': patterns,
            'suggestions': suggestions,
            'training_examples': count
        }


# ========== EJEMPLO DE USO ==========

def example_usage():
    """Ejemplo de cómo usar el sistema de learning"""
    
    # 1. Recoger feedback
    collector = FeedbackCollector()
    
    collector.collect_feedback(
        session_id='session_123',
        rating=5,  # Thumbs up!
        user_message='Cuánto sale el iPhone 15?',
        bot_response='El iPhone 15 de 128GB sale $1.200.000',
        feedback_type='rating'
    )
    
    collector.collect_feedback(
        session_id='session_124',
        rating=1,  # Thumbs down
        user_message='Tienen stock?',
        bot_response='No entendí tu pregunta',
        feedback_type='negative',
        comment='La respuesta no fue útil'
    )
    
    # 2. Ver stats
    stats = collector.get_feedback_stats(days=7)
    print(f"Satisfaction: {stats['satisfaction_rate']}%")
    
    # 3. Analizar y mejorar
    improver = AutoImprover()
    results = improver.run_improvement_cycle()
    
    print(f"\nSugerencias: {results['suggestions']}")


if __name__ == '__main__':
    example_usage()
