"""
Expense Tracker - OCR Processing

PURPOSE: Image processing and text extraction using Tesseract OCR
SCOPE: OCR processing, image preprocessing, and text extraction
DEPENDENCIES: pytesseract, cv2, PIL, numpy
"""

import asyncio
import cv2
import numpy as np
import pytesseract
import logging
from PIL import Image
import io
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class OCRProcessor:
    """Base class for OCR processing with common functionality."""
    
    @staticmethod
    async def process_image_with_ocr(image_bytes: bytes) -> str:
        """Extract text from image using OCR."""
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            
            loop = asyncio.get_running_loop()
            ocr_config = r'--oem 3 --psm 6 -l nld+eng'
            
            text = await loop.run_in_executor(
                None,
                lambda: pytesseract.image_to_string(gray, config=ocr_config)
            )
            
            return text
            
        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            return ""


class SourceIdentifier:
    """Identifies the source/type of receipt from OCR text."""
    
    @staticmethod
    def identify_source(text: str) -> str:
        """Identify the source of the OCR text (e.g., Revolut, ABN AMRO)."""
        text_lower = text.lower()
        
        # Revolut fingerprints
        if ('split bill' in text_lower and 
            ('points earned' in text_lower or 'kiosk' in text_lower or 'revolut' in text_lower)):
            logger.info("Identified source: Revolut")
            return 'Revolut'
        
        # ABN AMRO fingerprints
        abn_indicators = ['abn amro', 'payment terminal', 'execution', 
                         'tikkie payment request', 'nl50 abna']
        if any(indicator in text_lower for indicator in abn_indicators):
            # Differentiate between single view and list view
            if 'execution' in text_lower and 'from account' in text_lower:
                logger.info("Identified source: ABN_AMRO_SINGLE")
                return 'ABN_AMRO_SINGLE'
            
            # Check for list patterns (multiple amounts on different lines)
            if len(re.findall(r'-\s*\d+,\d{2}', text_lower)) > 1:
                logger.info("Identified source: ABN_AMRO_LIST")
                return 'ABN_AMRO_LIST'
            
            # Fallback for ABN if not clearly a list
            logger.info("Identified source: ABN_AMRO_SINGLE (Fallback)")
            return 'ABN_AMRO_SINGLE'
        
        logger.info("Identified source: Generic")
        return 'Generic'


class OCRProcessingService:
    """Main service for processing images with OCR and parsing expense data."""
    
    def __init__(self):
        from .parsers import (
            RevolutParser, ABNAmroSingleParser, 
            ABNAmroListParser, GenericParser
        )
        
        self.source_identifier = SourceIdentifier()
        self.parsers = {
            'Revolut': RevolutParser(),
            'ABN_AMRO_SINGLE': ABNAmroSingleParser(),
            'ABN_AMRO_LIST': ABNAmroListParser(),
            'Generic': GenericParser()
        }
    
    async def process_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Process an image and return parsed expense data."""
        try:
            # Extract text using OCR
            text = await OCRProcessor.process_image_with_ocr(image_bytes)
            if not text.strip():
                logger.warning("No text extracted from image")
                return []
            
            # Identify source and get appropriate parser
            source = self.source_identifier.identify_source(text)
            parser = self.parsers.get(source, self.parsers['Generic'])
            
            # Parse the expense data
            parsed_data = parser.parse(text)
            
            # Post-process results with FX rates
            final_results = []
            for item in parsed_data:
                fx_rate = await self._get_fx_rate(item.get('currency', 'EUR'), item.get('date'))
                item['fx_rate'] = fx_rate
                item['amount_eur'] = round(item.get('amount', 0.0) / fx_rate, 2) if fx_rate and item.get('amount') else 0.0
                item.setdefault('person', 'Közös')
                item.setdefault('beneficiary', '')
                final_results.append(item)

            return final_results
            
        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            return []
    
    async def _get_fx_rate(self, currency: str, target_date: str = None) -> float:
        """Get exchange rate with caching and fallback."""
        if currency == 'EUR':
            return 1.0
        
        from datetime import date
        from .config import config
        import aiosqlite
        import httpx
        
        target_date = target_date or date.today().isoformat()
        
        # Check cache first
        async with aiosqlite.connect(config.DB_FILE) as conn:
            cursor = await conn.execute(
                'SELECT rate FROM fx_rates WHERE date = ? AND currency = ?', 
                (target_date, currency)
            )
            cached = await cursor.fetchone()
            if cached:
                return cached[0]
        
        # Fetch from API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get('https://api.exchangerate-api.com/v4/latest/EUR')
                response.raise_for_status()
                data = response.json()
                rate = data.get('rates', {}).get(currency)
                
                if rate:
                    # Cache the rate
                    async with aiosqlite.connect(config.DB_FILE) as conn:
                        await conn.execute(
                            'INSERT OR REPLACE INTO fx_rates (date, currency, rate) VALUES (?, ?, ?)', 
                            (target_date, currency, rate)
                        )
                        await conn.commit()
                    return rate
                    
        except Exception as e:
            logger.error(f"FX rate API error: {e}")
        
        # Return fallback rate
        return config.FALLBACK_FX_RATES.get(currency, 1.0)