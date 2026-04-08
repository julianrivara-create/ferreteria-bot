import json
import os
import logging
import random
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

class ABTestingFramework:
    """
    Framework de A/B Testing para experimentar con variantes
    """
    
    def __init__(self, experiments_file: str = "experiments_config.json"):
        self.experiments_file = experiments_file
        self.experiments = self._load_experiments()
        
        # Resultados en memoria (en producción usar DB)
        self.results = defaultdict(lambda: {
            'variant_a': {'impressions': 0, 'conversions': 0},
            'variant_b': {'impressions': 0, 'conversions': 0}
        })
    
    def _load_experiments(self) -> Dict:
        """Carga configuración de experimentos"""
        if os.path.exists(self.experiments_file):
            try:
                with open(self.experiments_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        # Experimentos default
        return {
            "greeting_style": {
                "name": "Greeting Style Test",
                "active": True,
                "variant_a": {
                    "name": "Formal",
                    "value": "Buen día! ¿En qué puedo ayudarte?"
                },
                "variant_b": {
                    "name": "Informal",
                    "value": "Hola che! ¿Qué andás buscando?"
                },
                "traffic_split": 50,  # % para variant_a (resto va a variant_b)
                "goal": "conversion"
            },
            "upsell_timing": {
                "name": "Upsell Timing Test",
                "active": False,
                "variant_a": {
                    "name": "Early Upsell",
                    "value": "show_after_product_selection"
                },
                "variant_b": {
                    "name": "Late Upsell",
                    "value": "show_after_price_confirmation"
                },
                "traffic_split": 50,
                "goal": "upsell_acceptance"
            },
            "price_format": {
                "name": "Price Display Test",
                "active": True,
                "variant_a": {
                    "name": "With USD",
                    "value": "show_both_currencies"
                },
                "variant_b": {
                    "name": "ARS Only",
                    "value": "show_ars_only"
                },
                "traffic_split": 50,
                "goal": "conversion"
            }
        }
    
    def _save_experiments(self):
        """Guarda configuración"""
        with open(self.experiments_file, 'w', encoding='utf-8') as f:
            json.dump(self.experiments, f, indent=2)
    
    def get_variant(self, experiment_name: str, user_id: str) -> str:
        """
        Obtiene variante para un usuario
        
        Args:
            experiment_name: Nombre del experimento
            user_id: ID del usuario (session_id, email, etc.)
        
        Returns:
            'variant_a' o 'variant_b'
        """
        experiment = self.experiments.get(experiment_name)
        
        if not experiment or not experiment.get('active'):
            return 'variant_a'  # Default
        
        # Determinar variante basado en hash del user_id (consistente)
        hash_val = hash(user_id + experiment_name)
        split = experiment.get('traffic_split', 50)
        
        if (hash_val % 100) < split:
            variant = 'variant_a'
        else:
            variant = 'variant_b'
        
        # Registrar impresión
        self.results[experiment_name][variant]['impressions'] += 1
        
        logging.info(f"AB Test: {experiment_name} -> {variant} for user {user_id}")
        
        return variant
    
    def get_variant_value(self, experiment_name: str, user_id: str) -> Any:
        """
        Obtiene el valor de la variante asignada
        
        Returns:
            El valor configurado para la variante
        """
        variant = self.get_variant(experiment_name, user_id)
        experiment = self.experiments.get(experiment_name, {})
        
        return experiment.get(variant, {}).get('value')
    
    def track_conversion(self, experiment_name: str, user_id: str):
        """
        Registra una conversión para el experimento
        
        Args:
            experiment_name: Nombre del experimento
            user_id: ID del usuario
        """
        variant = self.get_variant(experiment_name, user_id)
        self.results[experiment_name][variant]['conversions'] += 1
        
        logging.info(f"AB Test conversion: {experiment_name} -> {variant}")
    
    def get_results(self, experiment_name: str) -> Dict:
        """
        Obtiene resultados del experimento
        
        Returns:
            {
                'variant_a': {'impressions': X, 'conversions': Y, 'rate': Z%},
                'variant_b': {...},
                'winner': 'variant_a' | 'variant_b' | 'inconclusive',
                'confidence': float
            }
        """
        if experiment_name not in self.results:
            return {'error': 'No data for this experiment'}
        
        data = self.results[experiment_name]
        
        # Calcular tasas de conversión
        a_rate = (data['variant_a']['conversions'] / data['variant_a']['impressions'] * 100
                  if data['variant_a']['impressions'] > 0 else 0)
        
        b_rate = (data['variant_b']['conversions'] / data['variant_b']['impressions'] * 100
                  if data['variant_b']['impressions'] > 0 else 0)
        
        # Determinar ganador (simplificado, sin test estadístico real)
        min_sample = 30  # Mínimo de impresiones para declarar ganador
        
        if (data['variant_a']['impressions'] < min_sample or 
            data['variant_b']['impressions'] < min_sample):
            winner = 'inconclusive'
            confidence = 0.0
        else:
            if abs(a_rate - b_rate) < 5:  # Diferencia <5% = inconclusive
                winner = 'inconclusive'
                confidence = 0.0
            elif a_rate > b_rate:
                winner = 'variant_a'
                confidence = min((a_rate - b_rate) / a_rate, 0.95)
            else:
                winner = 'variant_b'
                confidence = min((b_rate - a_rate) / b_rate, 0.95)
        
        return {
            'experiment': experiment_name,
            'variant_a': {
                **data['variant_a'],
                'conversion_rate': round(a_rate, 2)
            },
            'variant_b': {
                **data['variant_b'],
                'conversion_rate': round(b_rate, 2)
            },
            'winner': winner,
            'confidence': round(confidence, 2)
        }
    
    def create_experiment(self, name: str, config: Dict):
        """
        Crea un nuevo experimento
        
        Args:
            name: Nombre del experimento
            config: Configuración (variant_a, variant_b, traffic_split, goal)
        """
        self.experiments[name] = {
            'active': True,
            **config
        }
        self._save_experiments()
        logging.info(f"Created experiment: {name}")
    
    def stop_experiment(self, name: str):
        """Detiene un experimento"""
        if name in self.experiments:
            self.experiments[name]['active'] = False
            self._save_experiments()
            logging.info(f"Stopped experiment: {name}")
