#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Validate All Configuration
Checks that everything is properly configured
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Tuple, Dict

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from bot_sales.core.pretty_cli import (
        console, print_header, print_success,
        print_error, print_warning, print_info, create_table
    )
    PRETTY_CLI = True
except ImportError:
    PRETTY_CLI = False
    def print_header(msg, sub=""):
        print(f"\n{'='*60}\n{msg}\n{sub}\n{'='*60}")
    def print_success(msg): print(f"✅ {msg}")
    def print_error(msg): print(f"❌ {msg}")
    def print_warning(msg): print(f"⚠️  {msg}")
    def print_info(msg): print(f"ℹ️  {msg}")


class ConfigValidator:
    """Validates all configuration"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.root = Path(__file__).parent.parent
    
    def validate_all(self) -> bool:
        """
        Run all validations
        
        Returns:
            True if all validations pass
        """
        print_header("🔍 Configuration Validator", "Checking all settings...")
        
        checks = [
            ("Environment Files", self.check_env_files),
            ("Database Files", self.check_database_files),
            ("Python Dependencies", self.check_dependencies),
            ("Project Structure", self.check_project_structure),
            ("Config Files", self.check_config_files),
            ("Data Files", self.check_data_files)
        ]
        
        for name, check_func in checks:
            print_info(f"\nChecking {name}...")
            check_func()
        
        # Summary
        print("\n")
        print_header("📊 Validation Summary")
        
        if self.errors:
            print_error(f"Found {len(self.errors)} errors:")
            for error in self.errors:
                print_error(f"  • {error}")
        else:
            print_success("No errors found!")
        
        if self.warnings:
            print_warning(f"\nFound {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print_warning(f"  • {warning}")
        
        if not self.errors and not self.warnings:
            print_success("\n✨ All validations passed!")
            return True
        elif not self.errors:
            print_info("\n✅ No critical errors, but please review warnings")
            return True
        else:
            print_error("\n❌ Please fix errors before proceeding")
            return False
    
    def check_env_files(self) -> None:
        """Check environment files"""
        env_files = ['.env.example', '.env.development', '.env.production']
        
        for env_file in env_files:
            path = self.root / env_file
            if path.exists():
                print_success(f"{env_file} exists")
                
                # Check if it has required vars
                with open(path) as f:
                    content = f.read()
                    
                    required_vars = ['OPENAI_API_KEY', 'DATABASE_PATH', 'LOG_FILE']
                    for var in required_vars:
                        if var not in content:
                            self.warnings.append(f"{env_file} missing {var}")
            else:
                self.warnings.append(f"Missing {env_file}")
        
        # Check if .env exists
        if not (self.root / '.env').exists():
            self.warnings.append(".env not found - copy from .env.example")
    
    def check_database_files(self) -> None:
        """Check database files"""
        db_path = self.root / 'data' / 'iphone_store.db'
        
        if db_path.exists():
            print_success(f"Database exists: {db_path}")
            
            # Check size
            size_mb = db_path.stat().st_size / (1024 * 1024)
            print_info(f"  Size: {size_mb:.2f} MB")
            
            if size_mb == 0:
                self.warnings.append("Database is empty")
        else:
            self.warnings.append("Database not found - will be created on first run")
    
    def check_dependencies(self) -> None:
        """Check Python dependencies"""
        required_packages = [
            'openai', 'flask', 'pytest', 'requests',
            'google', 'twilio', 'redis', 'sentry_sdk',
            'cryptography', 'bcrypt'
        ]
        
        missing = []
        
        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                print_success(f"{package} installed")
            except ImportError:
                missing.append(package)
                print_warning(f"{package} NOT installed")
        
        if missing:
            self.warnings.append(f"Missing packages: {', '.join(missing)}")
            self.warnings.append("Run: pip install -r requirements.txt")
    
    def check_project_structure(self) -> None:
        """Check project directory structure"""
        required_dirs = [
            'bot_sales',
            'bot_sales/core',
            'bot_sales/security',
            'bot_sales/integrations',
            'tests',
            'data',
            'migrations',
            'docs'
        ]
        
        for dir_path in required_dirs:
            path = self.root / dir_path
            if path.exists():
                print_success(f"{dir_path}/ exists")
            else:
                self.errors.append(f"Missing directory: {dir_path}/")
    
    def check_config_files(self) -> None:
        """Check configuration files"""
        config_files = [
            'requirements.txt',
            'README.md',
            'docker-compose.yml',
            'Dockerfile'
        ]
        
        for config_file in config_files:
            path = self.root / config_file
            if path.exists():
                print_success(f"{config_file} exists")
            else:
                self.warnings.append(f"Missing {config_file}")
        
        # Check business_config.json if exists
        business_config = self.root / 'business_config.json'
        if business_config.exists():
            try:
                with open(business_config) as f:
                    config = json.load(f)
                    print_success("business_config.json is valid JSON")
                    
                    # Validate structure
                    if 'business' not in config:
                        self.warnings.append("business_config.json missing 'business' key")
            except json.JSONDecodeError:
                self.errors.append("business_config.json is invalid JSON")
    
    def check_data_files(self) -> None:
        """Check data files"""
        data_dir = self.root / 'data'
        
        if not data_dir.exists():
            self.errors.append("data/ directory missing")
            return
        
        # Check for products CSV
        csv_files = list(data_dir.glob('*.csv'))
        if csv_files:
            print_success(f"Found {len(csv_files)} CSV file(s)")
            for csv_file in csv_files:
                print_info(f"  {csv_file.name}")
        else:
            self.warnings.append("No product CSV files found in data/")
        
        # Check policies
        policies = data_dir / 'policies.md'
        if policies.exists():
            print_success("policies.md exists")
        else:
            self.warnings.append("policies.md not found")


def main():
    """Main entry point"""
    validator = ConfigValidator()
    success = validator.validate_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
