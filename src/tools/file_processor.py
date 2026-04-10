import os
from typing import List, Optional
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from PyPDF2 import PdfReader
from docx import Document
import pandas as pd
from openpyxl import load_workbook

from src.config import settings
from src.state import FileInfo


class FileProcessor:
    def __init__(self):
        self.supported_types = {
            '.pdf': self._extract_pdf,
            '.docx': self._extract_docx,
            '.doc': self._extract_docx,
            '.txt': self._extract_txt,
            '.xlsx': self._extract_xlsx,
            '.xls': self._extract_xlsx,
            '.csv': self._extract_csv,
        }
        self._executor = ThreadPoolExecutor(max_workers=4)
    
    def _get_file_type(self, file_path: str) -> str:
        return Path(file_path).suffix.lower()
    
    def _extract_pdf(self, file_path: str) -> str:
        try:
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            return f"PDF解析错误: {str(e)}"
    
    def _extract_docx(self, file_path: str) -> str:
        try:
            doc = Document(file_path)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    paragraphs.append(row_text)
            
            return "\n".join(paragraphs)
        except Exception as e:
            return f"DOCX解析错误: {str(e)}"
    
    def _extract_txt(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
        except Exception as e:
            return f"TXT解析错误: {str(e)}"
    
    def _extract_xlsx(self, file_path: str) -> str:
        try:
            wb = load_workbook(file_path, data_only=True)
            all_text = []
            
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                all_text.append(f"=== 工作表: {sheet_name} ===")
                
                for row in sheet.iter_rows(values_only=True):
                    row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                    if row_text.strip():
                        all_text.append(row_text)
            
            return "\n".join(all_text)
        except Exception as e:
            return f"XLSX解析错误: {str(e)}"
    
    def _extract_csv(self, file_path: str) -> str:
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk')
        
        return df.to_string(index=False)
    
    def extract_text(self, file_path: str) -> str:
        file_type = self._get_file_type(file_path)
        
        if file_type not in self.supported_types:
            return f"不支持的文件类型: {file_type}"
        
        extractor = self.supported_types[file_type]
        return extractor(file_path)
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP
        
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            
            if end < len(text):
                last_period = chunk.rfind('。')
                last_newline = chunk.rfind('\n')
                split_point = max(last_period, last_newline)
                
                if split_point > start + chunk_size // 2:
                    chunk = text[start:split_point + 1]
                    end = split_point + 1
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            start = end - overlap if end < len(text) else end
        
        return chunks
    
    def process_file(self, file_path: str) -> FileInfo:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        content = self.extract_text(file_path)
        chunks = self.chunk_text(content)
        
        return FileInfo(
            file_path=file_path,
            file_type=self._get_file_type(file_path),
            content=content,
            chunks=chunks
        )
    
    async def process_file_async(self, file_path: str) -> FileInfo:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.process_file, file_path)
    
    async def process_files_async(self, file_paths: List[str]) -> List[FileInfo]:
        tasks = [self.process_file_async(fp) for fp in file_paths]
        return await asyncio.gather(*tasks)
    
    def process_files(self, file_paths: List[str]) -> List[FileInfo]:
        results = []
        for fp in file_paths:
            try:
                result = self.process_file(fp)
                results.append(result)
            except Exception as e:
                results.append(FileInfo(
                    file_path=fp,
                    file_type="error",
                    content=f"处理错误: {str(e)}",
                    chunks=[]
                ))
        return results


file_processor = FileProcessor()
