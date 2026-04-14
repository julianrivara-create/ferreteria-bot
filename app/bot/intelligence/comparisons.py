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
            'brand', 'material', 'size', 'color',
            'price_ars', 'category'
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
                           marca1: str = None, marca2: str = None) -> Dict:
        """
        Compara por modelo y marca (más flexible)
        """
        # Buscar productos
        matches1 = self.db.find_matches(modelo1, marca=marca1)
        matches2 = self.db.find_matches(modelo2, marca=marca2)
        
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
        
        # Marca
        if p1.get('brand') != p2.get('brand'):
            diffs['brand'] = {
                'p1': p1.get('brand') or 'Sin marca',
                'p2': p2.get('brand') or 'Sin marca',
            }
        
        # Material
        if p1.get('material') != p2.get('material'):
            diffs['material'] = {
                'p1': p1.get('material') or '-',
                'p2': p2.get('material') or '-',
            }
        
        # Medida
        if p1.get('size') != p2.get('size'):
            diffs['size'] = {
                'p1': p1.get('size') or '-',
                'p2': p2.get('size') or '-',
            }
        
        # Precio
        price1 = p1.get('price_ars', 0)
        price2 = p2.get('price_ars', 0)
        if price1 != price2:
            diff_pct = abs(price1 - price2) / max(min(price1, price2), 1) * 100
            diffs['price'] = {
                'p1': price1,
                'p2': price2,
                'difference_ars': abs(price1 - price2),
                'difference_pct': round(diff_pct, 1),
                'cheaper': 'p1' if price1 < price2 else 'p2'
            }
        
        # Categoría
        if p1.get('category') != p2.get('category'):
            diffs['category'] = {
                'p1': p1.get('category'),
                'p2': p2.get('category')
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
        
        # Marca diferente
        if 'brand' in diffs:
            recommendations.append(f"🏷️ Marcas distintas: {diffs['brand']['p1']} vs {diffs['brand']['p2']}")
        
        # Material
        if 'material' in diffs:
            recommendations.append(f"🔧 Material: {diffs['material']['p1']} vs {diffs['material']['p2']}")
        
        # Medida
        if 'size' in diffs:
            recommendations.append(f"📏 Medida: {diffs['size']['p1']} vs {diffs['size']['p2']}")
        
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
        
        # Marca
        b1 = p1.get('brand') or '-'
        b2 = p2.get('brand') or '-'
        lines.append(f"{'Marca':<15} | {b1:<20} | {b2:<20}")
        
        # Medida
        sz1 = p1.get('size') or '-'
        sz2 = p2.get('size') or '-'
        lines.append(f"{'Medida':<15} | {sz1:<20} | {sz2:<20}")
        
        # Material
        m1 = p1.get('material') or '-'
        m2 = p2.get('material') or '-'
        lines.append(f"{'Material':<15} | {m1:<20} | {m2:<20}")
        
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
