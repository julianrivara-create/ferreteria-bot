import os
import shutil
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List

class BackupSystem:
    """
    Sistema de backups automáticos
    """
    
    def __init__(self, db_file: str = "data/ferreteria.db", 
                 backup_dir: str = "backups",
                 retention_days: int = 30):
        self.db_file = db_file
        self.backup_dir = backup_dir
        self.retention_days = retention_days
        
        # Crear directorio de backups
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self) -> Dict:
        """
        Crea backup de la base de datos
        
        Returns:
            {
                'status': 'success' | 'error',
                'backup_file': str,
                'size_mb': float,
                'timestamp': str
            }
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"backup_{timestamp}.db")
            
            # Copiar DB
            shutil.copy2(self.db_file, backup_file)
            
            # Calcular tamaño
            size_bytes = os.path.getsize(backup_file)
            size_mb = size_bytes / (1024 * 1024)
            
            # También hacer backup de config files
            self._backup_config_files(timestamp)
            
            logging.info(f"Backup created: {backup_file} ({size_mb:.2f} MB)")
            
            return {
                'status': 'success',
                'backup_file': backup_file,
                'size_mb': round(size_mb, 2),
                'timestamp': timestamp
            }
        
        except Exception as e:
            logging.error(f"Backup failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _backup_config_files(self, timestamp: str):
        """Backup de archivos de configuración"""
        config_files = [
            'catalog.csv',
            'catalog_extended.csv',
            'policies.md',
            'bundles.json'
        ]
        
        config_backup_dir = os.path.join(self.backup_dir, f"config_{timestamp}")
        os.makedirs(config_backup_dir, exist_ok=True)
        
        for file in config_files:
            if os.path.exists(file):
                shutil.copy2(file, os.path.join(config_backup_dir, file))
    
    def list_backups(self) -> List[Dict]:
        """
        Lista todos los backups disponibles
        
        Returns:
            [{
                'file': str,
                'timestamp': str,
                'size_mb': float,
                'age_days': int
            }]
        """
        backups = []
        
        for file in os.listdir(self.backup_dir):
            if file.startswith('backup_') and file.endswith('.db'):
                file_path = os.path.join(self.backup_dir, file)
                
                # Obtener timestamp del archivo
                mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                age_days = (datetime.now() - mod_time).days
                
                size_bytes = os.path.getsize(file_path)
                size_mb = size_bytes / (1024 * 1024)
                
                backups.append({
                    'file': file,
                    'timestamp': mod_time.strftime("%Y-%m-%d %H:%M:%S"),
                    'size_mb': round(size_mb, 2),
                    'age_days': age_days
                })
        
        # Ordenar por más reciente
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return backups
    
    def restore_backup(self, backup_file: str) -> Dict:
        """
        Restaura un backup
        
        Args:
            backup_file: Nombre del archivo de backup (sin path)
        
        Returns:
            {
                'status': 'success' | 'error',
                'message': str
            }
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_file)
            
            if not os.path.exists(backup_path):
                return {
                    'status': 'error',
                    'message': f'Backup file not found: {backup_file}'
                }
            
            # Crear backup del estado actual antes de restaurar
            self.create_backup()
            
            # Restaurar
            shutil.copy2(backup_path, self.db_file)
            
            logging.info(f"Restored backup: {backup_file}")
            
            return {
                'status': 'success',
                'message': f'Database restored from {backup_file}'
            }
        
        except Exception as e:
            logging.error(f"Restore failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def cleanup_old_backups(self) -> Dict:
        """
        Elimina backups antiguos según retention policy
        
        Returns:
            {
                'deleted_count': int,
                'deleted_files': []
            }
        """
        deleted = []
        
        for backup in self.list_backups():
            if backup['age_days'] > self.retention_days:
                file_path = os.path.join(self.backup_dir, backup['file'])
                os.remove(file_path)
                deleted.append(backup['file'])
                
                logging.info(f"Deleted old backup: {backup['file']}")
        
        return {
            'deleted_count': len(deleted),
            'deleted_files': deleted
        }
    
    def verify_backup(self, backup_file: str) -> bool:
        """
        Verifica integridad de un backup
        
        Returns:
            True si el backup es válido
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_file)
            
            # Intentar abrir la DB
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            
            # Ejecutar query simple para verificar
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            conn.close()
            
            # Debe tener al menos algunas tablas
            return len(tables) >= 3
        
        except:
            return False
