import logging
import logging.handlers
import json
import os
from datetime import datetime
from pathlib import Path

class JsonFormatter(logging.Formatter):
    """
    Formatter que convierte logs a JSON estructurado
    """
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Agregar exception info si existe
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Agregar datos extra
        if hasattr(record, 'session_id'):
            log_data['session_id'] = record.session_id
        
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        
        return json.dumps(log_data, ensure_ascii=False)


class BotLogger:
    """
    Sistema de logging mejorado para el bot
    """
    
    def __init__(self, log_dir: str = "logs", app_name: str = "sales_bot"):
        self.log_dir = Path(log_dir)
        self.app_name = app_name
        
        # Crear directorio de logs
        self.log_dir.mkdir(exist_ok=True)
        
        # Setup loggers
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Configura los loggers"""
        
        # Root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Limpiar handlers existentes
        root_logger.handlers = []
        
        # 1. Console Handler (human-readable)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # 2. File Handler - JSON (para parsing)
        json_log_file = self.log_dir / f"{self.app_name}.json.log"
        json_handler = logging.handlers.RotatingFileHandler(
            json_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        json_handler.setLevel(logging.INFO)
        json_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(json_handler)
        
        # 3. File Handler - Text (human-readable)
        text_log_file = self.log_dir / f"{self.app_name}.log"
        text_handler = logging.handlers.RotatingFileHandler(
            text_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        text_handler.setLevel(logging.INFO)
        text_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        text_handler.setFormatter(text_formatter)
        root_logger.addHandler(text_handler)
        
        # 4. Error Handler (solo errores)
        error_log_file = self.log_dir / f"{self.app_name}.error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(text_formatter)
        root_logger.addHandler(error_handler)
        
        logging.info(f"Logger initialized. Logs dir: {self.log_dir.absolute()}")
    
    def get_logger(self, name: str):
        """Obtiene un logger específico"""
        return logging.getLogger(name)
    
    def set_level(self, level: str):
        """Cambia el nivel de logging global"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        log_level = level_map.get(level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        logging.info(f"Log level changed to: {level}")
    
    def log_user_message(self, session_id: str, message: str):
        """Log de mensaje de usuario"""
        logger = logging.getLogger('bot.messages')
        logger.info(
            f"User message: {message[:100]}...",
            extra={'session_id': session_id, 'action': 'user_message'}
        )
    
    def log_bot_response(self, session_id: str, response: str):
        """Log de respuesta del bot"""
        logger = logging.getLogger('bot.messages')
        logger.info(
            f"Bot response: {response[:100]}...",
            extra={'session_id': session_id, 'action': 'bot_response'}
        )
    
    def log_function_call(self, session_id: str, function_name: str, args: dict):
        """Log de function call"""
        logger = logging.getLogger('bot.functions')
        logger.info(
            f"Function called: {function_name} with args: {args}",
            extra={'session_id': session_id, 'action': 'function_call'}
        )
    
    def log_sale(self, session_id: str, sale_id: str, amount: float):
        """Log de venta"""
        logger = logging.getLogger('bot.sales')
        logger.info(
            f"Sale completed: {sale_id} - Amount: ${amount}",
            extra={'session_id': session_id, 'action': 'sale_completed'}
        )
    
    def log_error(self, error: Exception, context: dict = None):
        """Log de error con contexto"""
        logger = logging.getLogger('bot.errors')
        extra_info = context or {}
        logger.error(
            f"Error occurred: {str(error)}",
            exc_info=True,
            extra={'action': 'error', **extra_info}
        )


# Singleton global
_bot_logger = None

def get_logger(name: str = None):
    """
    Obtiene el logger global del bot
    
    Usage:
        from bot_sales.core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Message")
    """
    global _bot_logger
    
    if _bot_logger is None:
        _bot_logger = BotLogger()
    
    if name:
        return _bot_logger.get_logger(name)
    
    return logging.getLogger()


def setup_logging(log_dir: str = "logs", level: str = "INFO"):
    """
    Setup inicial del sistema de logging
    
    Llamar al inicio de la aplicación:
        from bot_sales.core.logger import setup_logging
        setup_logging(level="DEBUG")
    """
    global _bot_logger
    _bot_logger = BotLogger(log_dir=log_dir)
    _bot_logger.set_level(level)
    return _bot_logger
