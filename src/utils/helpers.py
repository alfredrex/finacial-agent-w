import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging

from src.config import settings


class Logger:
    def __init__(self, name: str = "FinancialAgent"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def debug(self, message: str):
        self.logger.debug(message)


logger = Logger()


class CacheManager:
    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or settings.DATA_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        safe_key = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in key)
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def get(self, key: str, max_age: int = 3600) -> Optional[Any]:
        cache_path = self._get_cache_path(key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cached_time = data.get("timestamp", 0)
            current_time = datetime.now().timestamp()
            
            if current_time - cached_time > max_age:
                return None
            
            return data.get("value")
            
        except Exception:
            return None
    
    def set(self, key: str, value: Any):
        cache_path = self._get_cache_path(key)
        
        try:
            data = {
                "timestamp": datetime.now().timestamp(),
                "value": value
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                
        except Exception:
            pass
    
    def delete(self, key: str):
        cache_path = self._get_cache_path(key)
        
        if os.path.exists(cache_path):
            os.remove(cache_path)
    
    def clear(self):
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                os.remove(os.path.join(self.cache_dir, filename))


cache_manager = CacheManager()


def format_number(value: float, decimal: int = 2) -> str:
    if value is None:
        return "N/A"
    
    if abs(value) >= 1e8:
        return f"{value / 1e8:.{decimal}f}亿"
    elif abs(value) >= 1e4:
        return f"{value / 1e4:.{decimal}f}万"
    else:
        return f"{value:.{decimal}f}"


def format_percent(value: float, decimal: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimal}f}%"


def format_timestamp(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp
