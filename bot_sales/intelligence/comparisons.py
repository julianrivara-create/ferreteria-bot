import logging
from typing import Dict, List, Any
from ..core.database import Database

class ProductComparator:
    """
    Motor de comparación de productos
    """
    
    def __init__(self, db: Database):
        self.db = db
        
        # Features importantes para comparación
        self.key_features = [
            'storage_gb', 'color', 'generation', 'camera_mp',
            'price_usd', 'price_ars', 'category'
        ]
    
    def compare_products(self, sku1: str, sku2: str) -> Dict[str, Any]:
        """
        Compara dos productos lado a lado
        
        Returns:
            {
                'status': 'success' | 'error',
                'product1': {...},
                'product2': {...},
                'differences': {...},
                'recommendation': str
            }
        """
        # Obtener productos
        p1 = self.db.get_product_by_sku(sku1)
        p2 = self.db.get_product_by_sku(sku2)
        
        if not p1 or not p2:
            return {
                'status': 'error',
                'message': 'Uno o ambos productos no encontrados'
            }
        
        # Calcular diferencias
        differences = self._calculate_differences(p1, p2)
        
        # Generar recomendación
        recommendation = self._generate_recommendation(p1, p2, differences)
        
        return {
            'status': 'success',
            'product1': p1,
            'product2': p2,
            'differences': differences,
            'recommendation': recommendation,
            'comparison_table': self._format_comparison_table(p1, p2, differences)
        }
    
    def compare_by_criteria(self, modelo1: str, modelo2: str, 
                           storage1: int = None, storage2: int = None) -> Dict:
        """
        Compara por modelo y storage (más flexible)
        """
        # Buscar productos
        matches1 = self.db.find_matches(modelo1, storage1, None)
        matches2 = self.db.find_matches(modelo2, storage2, None)
        
        if not matches1 or not matches2:
            return {
                'status': 'error',
                'message': 'No se encontraron productos para comparar'
            }
        
        # Usar primeros matches
        return self.compare_products(matches1[0]['sku'], matches2[0]['sku'])
    
    def _calculate_differences(self, p1: Dict, p2: Dict) -> Dict:
        """
        Calcula diferencias clave entre productos
        """
        diffs = {}
        
        # Storage
        if p1.get('storage_gb') != p2.get('storage_gb'):
            diffs['storage'] = {
                'p1': p1.get('storage_gb'),
                'p2': p2.get('storage_gb'),
                'winner': 'p1' if p1.get('storage_gb', 0) > p2.get('storage_gb', 0) else 'p2'
            }
        
        # Precio
        price1 = p1.get('price_ars', 0)
        price2 = p2.get('price_ars', 0)
        if price1 != price2:
            diff_pct = abs(price1 - price2) / min(price1, price2) * 100
            diffs['price'] = {
                'p1': price1,
                'p2': price2,
                'difference_ars': abs(price1 - price2),
                'difference_pct': round(diff_pct, 1),
                'cheaper': 'p1' if price1 < price2 else 'p2'
            }
        
        # Generación (detectar del modelo)
        gen1 = self._extract_generation(p1.get('model', ''))
        gen2 = self._extract_generation(p2.get('model', ''))
        if gen1 != gen2:
            diffs['generation'] = {
                'p1': gen1,
                'p2': gen2,
                'newer': 'p1' if gen1 > gen2 else 'p2'
            }
        
        # Color
        if p1.get('color') != p2.get('color'):
            diffs['color'] = {
                'p1': p1.get('color'),
                'p2': p2.get('color')
            }
        
        return diffs
    
    def _extract_generation(self, model: str) -> int:
        """Extrae número de generación/versión del modelo (ej: Taladro X500 -> 500)"""
        import re
        match = re.search(r'(\d+)', model)
        return int(match.group(1)) if match else 0
    
    def _generate_recommendation(self, p1: Dict, p2: Dict, diffs: Dict) -> str:
        """
        Genera recomendación basada en diferencias
        """
        recommendations = []
        
        # Mejor valor (value for money)
        if 'price' in diffs:
            price_diff_pct = diffs['price']['difference_pct']
            if price_diff_pct > 20:
                cheaper = 'product1' if diffs['price']['cheaper'] == 'p1' else 'product2'
                recommendations.append(f"✅ {p1['model'] if cheaper == 'product1' else p2['model']} tiene mejor precio ({price_diff_pct}% más barato)")
        
        # Más moderno
        if 'generation' in diffs:
            newer = 'product1' if diffs['generation']['newer'] == 'p1' else 'product2'
            model_newer = p1['model'] if newer == 'product1' else p2['model']
            recommendations.append(f"🆕 {model_newer} es más nuevo")
        
        # Más storage
        if 'storage' in diffs:
            more_storage = 'product1' if diffs['storage']['winner'] == 'p1' else 'product2'
            model_storage = p1['model'] if more_storage == 'product1' else p2['model']
            storage = p1['storage_gb'] if more_storage == 'product1' else p2['storage_gb']
            recommendations.append(f"💾 {model_storage} tiene más capacidad ({storage}GB)")
        
        if not recommendations:
            return "Ambos productos son muy similares. Elegí según tu preferencia de color o disponibilidad."
        
        return "\n".join(recommendations)
    
    def _format_comparison_table(self, p1: Dict, p2: Dict, diffs: Dict) -> str:
        """
        Formatea tabla de comparación para mostrar al usuario
        """
        lines = []
        lines.append(f"📊 COMPARACIÓN\n")
        lines.append(f"{'Feature':<15} | {p1.get('model', ''):<20} | {p2.get('model', ''):<20}")
        lines.append("-" * 60)
        
        # Modelo
        lines.append(f"{'Modelo':<15} | {p1.get('model', '-'):<20} | {p2.get('model', '-'):<20}")
        
        # Storage
        s1 = f"{p1.get('storage_gb', 0)}GB"
        s2 = f"{p2.get('storage_gb', 0)}GB"
        winner = " ✓" if diffs.get('storage', {}).get('winner') == 'p1' else ""
        s1 += winner
        winner = " ✓" if diffs.get('storage', {}).get('winner') == 'p2' else ""
        s2 += winner
        lines.append(f"{'Storage':<15} | {s1:<20} | {s2:<20}")
        
        # Precio
        price1 = f"${p1.get('price_ars', 0):,}".replace(",", ".")
        price2 = f"${p2.get('price_ars', 0):,}".replace(",", ".")
        winner = " ✓" if diffs.get('price', {}).get('cheaper') == 'p1' else ""
        price1 += winner
        winner = " ✓" if diffs.get('price', {}).get('cheaper') == 'p2' else ""
        price2 += winner
        lines.append(f"{'Precio':<15} | {price1:<20} | {price2:<20}")
        
        # Color
        lines.append(f"{'Color':<15} | {p1.get('color', '-'):<20} | {p2.get('color', '-'):<20}")
        
        return "\n".join(lines)
