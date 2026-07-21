"""
檔案解析工具
支援PDF、Markdown、TXT檔案的文字提取
"""

import os
from pathlib import Path
from typing import List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    讀取文字檔案，UTF-8失敗時自動探測編碼。
    
    採用多級回退策略：
    1. 首先嚐試 UTF-8 解碼
    2. 使用 charset_normalizer 檢測編碼
    3. 回退到 chardet 檢測編碼
    4. 最終使用 UTF-8 + errors='replace' 兜底
    
    Args:
        file_path: 檔案路徑
        
    Returns:
        解碼後的文字內容
    """
    data = Path(file_path).read_bytes()
    
    # 首先嚐試 UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # 嘗試使用 charset_normalizer 檢測編碼
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass
    
    # 回退到 chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass
    
    # 最終兜底：使用 UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'
    
    return data.decode(encoding, errors='replace')


class FileParser:
    """檔案解析器"""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}
    
    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        從檔案中提取文字
        
        Args:
            file_path: 檔案路徑
            
        Returns:
            提取的文字內容
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"檔案不存在: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支援的檔案格式: {suffix}")
        
        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)
        
        raise ValueError(f"無法處理的檔案格式: {suffix}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """從PDF提取文字"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("需要安裝PyMuPDF: pip install PyMuPDF")
        
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """從Markdown提取文字，支援自動編碼檢測"""
        return _read_text_with_fallback(file_path)
    
    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """從TXT提取文字，支援自動編碼檢測"""
        return _read_text_with_fallback(file_path)
    
    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        從多個檔案提取文字併合並
        
        Args:
            file_paths: 檔案路徑列表
            
        Returns:
            合併後的文字
        """
        all_texts = []
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== 檔案 {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== 檔案 {i}: {file_path} (提取失敗: {str(e)}) ===")
        
        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str, 
    chunk_size: int = 500, 
    overlap: int = 50
) -> List[str]:
    """
    將文字分割成小塊
    
    Args:
        text: 原始文字
        chunk_size: 每塊的字元數
        overlap: 重疊字元數
        
    Returns:
        文字塊列表
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # 嘗試在句子邊界處分割
        if end < len(text):
            # 查詢最近的句子結束符
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # 下一個塊從重疊位置開始
        start = end - overlap if end < len(text) else len(text)
    
    return chunks

