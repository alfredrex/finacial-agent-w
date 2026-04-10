import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    OPENAI_API_KEY: str = Field(default="", description="LLM API密钥(DeepSeek)")
    OPENAI_BASE_URL: Optional[str] = Field(default="https://api.deepseek.com/v1", description="LLM API基础URL")
    OPENAI_MODEL: str = Field(default="deepseek-chat", description="使用的LLM模型名称")
    
    EMBEDDING_MODEL: str = Field(default="text-embedding-3-small", description="嵌入模型名称")
    EMBEDDING_BASE_URL: Optional[str] = Field(default=None, description="嵌入模型API基础URL")
    EMBEDDING_API_KEY: Optional[str] = Field(default=None, description="嵌入模型API密钥")
    
    CHROMA_DB_PATH: str = Field(default="./chromadb", description="ChromaDB存储路径")
    CHROMA_COLLECTION_NAME: str = Field(default="financial_docs", description="ChromaDB集合名称")
    
    CHUNK_SIZE: int = Field(default=1000, description="文档分块大小")
    CHUNK_OVERLAP: int = Field(default=200, description="文档分块重叠大小")
    
    SYSTEM_TIMEOUT: int = Field(default=30000, description="系统超时时间(毫秒)")
    MAX_RETRY: int = Field(default=3, description="最大重试次数")
    
    HTTP_PROXY: Optional[str] = Field(default=None, description="HTTP代理")
    HTTPS_PROXY: Optional[str] = Field(default=None, description="HTTPS代理")
    
    MAX_TOKENS: int = Field(default=4096, description="最大生成token数")
    TEMPERATURE: float = Field(default=0.7, description="生成温度")
    
    DATA_CACHE_DIR: str = Field(default="./data_cache", description="数据缓存目录")
    REPORT_OUTPUT_DIR: str = Field(default="./reports", description="报告输出目录")
    
    TUSHARE_TOKEN: Optional[str] = Field(default=None, description="Tushare API Token")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

os.makedirs(settings.DATA_CACHE_DIR, exist_ok=True)
os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DB_PATH, exist_ok=True)
