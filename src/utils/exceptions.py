from functools import wraps
from typing import Callable, Any
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings


class FinancialSystemError(Exception):
    pass


class LLMError(FinancialSystemError):
    pass


class DataCollectionError(FinancialSystemError):
    pass


class AnalysisError(FinancialSystemError):
    pass


class FileProcessingError(FinancialSystemError):
    pass


class RAGError(FinancialSystemError):
    pass


def async_retry(
    max_attempts: int = None,
    wait_min: int = 1,
    wait_max: int = 10,
    exceptions: tuple = (Exception,)
):
    max_attempts = max_attempts or settings.MAX_RETRY
    
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            retry=retry_if_exception_type(exceptions),
            reraise=True
        )
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = None,
    wait_min: int = 1,
    wait_max: int = 10,
    exceptions: tuple = (Exception,)
):
    max_attempts = max_attempts or settings.MAX_RETRY
    
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            retry=retry_if_exception_type(exceptions),
            reraise=True
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def fallback(default_value: Any = None):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return default_value
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return default_value
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


class ErrorHandler:
    def __init__(self):
        self.error_counts = {}
    
    def handle_error(self, error: Exception, context: str = "") -> dict:
        error_type = type(error).__name__
        error_message = str(error)
        
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
        
        return {
            "error_type": error_type,
            "error_message": error_message,
            "context": context,
            "count": self.error_counts[error_type]
        }
    
    def get_error_stats(self) -> dict:
        return self.error_counts.copy()
    
    def clear_stats(self):
        self.error_counts.clear()


error_handler = ErrorHandler()
