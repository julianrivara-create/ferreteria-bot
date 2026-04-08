import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

class FraudDetector:
    """
    Sistema de detección de fraude
    """
    
    def __init__(self, blacklist_file: str = "fraud_blacklist.json"):
        self.blacklist_file = blacklist_file
        self.blacklist = self._load_blacklist()
        
        # Rate limiting en memoria (en producción usar Redis)
        self.request_history = defaultdict(list)
        
        # Configuración
        self.max_requests_per_hour = 10
        self.max_requests_per_day = 50
        self.suspicious_keywords = [
            'test', 'prueba', 'fake', 'falso', 'hack'
        ]
    
    def _load_blacklist(self) -> Dict:
        """Carga blacklist desde archivo"""
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        
        return {
            "emails": [],
            "phones": [],
            "ips": []
        }
    
    def _save_blacklist(self):
        """Guarda blacklist a archivo"""
        with open(self.blacklist_file, 'w', encoding='utf-8') as f:
            json.dump(self.blacklist, f, indent=2)
    
    def check_blacklist(self, email: str = None, phone: str = None, ip: str = None) -> Tuple[bool, str]:
        """
        Verifica si email/phone/ip está en blacklist
        
        Returns:
            (is_blocked, reason)
        """
        if email and email.lower() in self.blacklist["emails"]:
            return True, "Email bloqueado por actividad sospechosa"
        
        if phone and phone in self.blacklist["phones"]:
            return True, "Teléfono bloqueado por actividad sospechosa"
        
        if ip and ip in self.blacklist["ips"]:
            return True, "IP bloqueada por actividad sospechosa"
        
        return False, ""
    
    def add_to_blacklist(self, email: str = None, phone: str = None, ip: str = None):
        """Agrega a blacklist"""
        if email:
            self.blacklist["emails"].append(email.lower())
        if phone:
            self.blacklist["phones"].append(phone)
        if ip:
            self.blacklist["ips"].append(ip)
        
        self._save_blacklist()
        logging.warning(f"Added to blacklist: email={email}, phone={phone}, ip={ip}")
    
    def check_rate_limit(self, identifier: str) -> Tuple[bool, str]:
        """
        Verifica rate limiting
        
        Args:
            identifier: Email, phone, o IP
        
        Returns:
            (is_allowed, reason)
        """
        now = datetime.now()
        
        # Limpiar requests antiguos
        self.request_history[identifier] = [
            ts for ts in self.request_history[identifier]
            if now - ts < timedelta(days=1)
        ]
        
        # Contar requests
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        recent_hour = sum(1 for ts in self.request_history[identifier] if ts > hour_ago)
        recent_day = len(self.request_history[identifier])
        
        if recent_hour >= self.max_requests_per_hour:
            return False, f"Demasiados intentos ({recent_hour}/h). Esperá un poco."
        
        if recent_day >= self.max_requests_per_day:
            return False, f"Límite diario alcanzado ({recent_day}/día)."
        
        # Registrar request
        self.request_history[identifier].append(now)
        
        return True, ""
    
    def detect_suspicious_content(self, message: str) -> Tuple[bool, str]:
        """
        Detecta contenido sospechoso en mensajes
        
        Returns:
            (is_suspicious, reason)
        """
        message_lower = message.lower()
        
        # Buscar keywords sospechosas
        for keyword in self.suspicious_keywords:
            if keyword in message_lower:
                return True, f"Keyword sospechosa detectada: {keyword}"
        
        # Detectar URLs sospechosas
        if 'http://' in message_lower or 'https://' in message_lower:
            return True, "URL detectada en mensaje"
        
        # Detectar repetición excesiva
        if len(message) > 10 and len(set(message)) < len(message) * 0.3:
            return True, "Repetición excesiva de caracteres"
        
        return False, ""
    
    def calculate_risk_score(self, 
                            email: str = None,
                            phone: str = None,
                            message: str = None,
                            ip: str = None) -> Tuple[int, List[str]]:
        """
        Calcula score de riesgo (0-100)
        
        Returns:
            (score, [reasons])
        """
        score = 0
        reasons = []
        
        # Blacklist check (+100)
        is_blocked, reason = self.check_blacklist(email, phone, ip)
        if is_blocked:
            score = 100
            reasons.append(reason)
            return score, reasons
        
        # Rate limiting (+50)
        identifier = email or phone or ip or "unknown"
        is_allowed, reason = self.check_rate_limit(identifier)
        if not is_allowed:
            score += 50
            reasons.append(reason)
        
        # Contenido sospechoso (+30)
        if message:
            is_suspicious, reason = self.detect_suspicious_content(message)
            if is_suspicious:
                score += 30
                reasons.append(reason)
        
        # Email temporal/desechable (+20)
        if email:
            temp_domains = ['tempmail', 'throwaway', '10minutemail', 'guerrillamail']
            if any(domain in email.lower() for domain in temp_domains):
                score += 20
                reasons.append("Email temporal detectado")
        
        return score, reasons
    
    def should_block(self, risk_score: int) -> bool:
        """
        Determina si debe bloquear basado en score
        
        Score:
        - 0-30: Bajo riesgo (permitir)
        - 31-60: Medio riesgo (advertir pero permitir)
        - 61-100: Alto riesgo (bloquear)
        """
        return risk_score > 60
