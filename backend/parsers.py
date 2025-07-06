"""
Expense Tracker - Receipt Parsers

PURPOSE: Specialized parsers for different receipt types and sources
SCOPE: Text parsing logic for Revolut, ABN AMRO, and generic receipts
DEPENDENCIES: re, datetime, logging
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExpenseParser:
    """Base class for expense parsing with common utilities."""
    
    @staticmethod
    def smart_categorize(text: str) -> str:
        """Enhanced smart categorization with better keyword matching."""
        text_lower = text.lower()
        category_map = {
            'Restaurants': ['restaurant', 'pizzeria', 'pompernikkel', 'eetcafe'],
            'Groceries': ['supermarket', 'albert heijn', 'jumbo', 'lidl', 'aldi', 'global supermarkt'],
            'Household': ['household', 'bakkerij', 'kiosk', 'sapn'],
            'Caffeine': ['coffee', 'cafe', 'koffie', 'starbucks', 'espresso'],
            'Car': ['fuel', 'gas', 'petrol', 'parking', 'sanef', 'autoroute', 'esso', 'rouenpalaisauto'],
            'Transport': ['transport', 'taxi', 'uber', 'bus', 'train'],
            'Sport': ['zwembad', 'swimming', 'gym', 'fitness', 'sport', 'tennis', 'voetbal', 'hockey']
        }
        
        for category, keywords in category_map.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        return 'Other'
    
    @staticmethod
    def clean_description(description: str) -> str:
        """Clean description by removing technical codes and combining meaningful parts."""
        if not description:
            return description
        
        # Remove technical codes and noise
        noise_patterns = [
            r',PAS\d+',  # Remove ,PAS011 type codes
            r'^BEA,\s*',  # Remove BEA prefix
            r'\s*,\s*$',  # Remove trailing commas
        ]
        
        cleaned = description
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Combine meaningful parts (e.g., SAPN + Google Pay)
        if 'sapn' in cleaned.lower() and 'google pay' in cleaned.lower():
            # Extract the parts and combine cleanly
            parts = re.split(r'[,\s]+', cleaned)
            meaningful_parts = [part for part in parts if part and not re.match(r'^(bea|pas\d+)$', part.lower())]
            if len(meaningful_parts) > 1:
                cleaned = ' '.join(meaningful_parts)
        
        return cleaned.strip()
    
    @staticmethod
    def detect_relative_date(text: str) -> Optional[str]:
        """Detect relative date indicators that should be left empty."""
        text_lower = text.lower()
        relative_indicators = ['today', 'yesterday', 'vandaag', 'gisteren', 'this morning', 'vanmorgen']
        
        for indicator in relative_indicators:
            if indicator in text_lower:
                return indicator
        return None
    
    @staticmethod
    def parse_european_amount(amount_str: str) -> Optional[float]:
        """Parse European number format amounts more robustly."""
        if not amount_str:
            return None
        
        # Remove currency symbols and extra whitespace
        cleaned = re.sub(r'[€$£-]', '', amount_str).strip()
        
        # Handle European format: 1.524,55 or 1,524.55
        # If there are both dots and commas, determine which is decimal
        if '.' in cleaned and ',' in cleaned:
            # European format: thousands separator = ., decimal = ,
            if cleaned.rfind(',') > cleaned.rfind('.'):
                # Last comma is decimal separator
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # Last dot is decimal separator
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            # Could be decimal comma (European) or thousands separator
            comma_pos = cleaned.rfind(',')
            after_comma = cleaned[comma_pos + 1:]
            
            # If 2 digits after comma, it's likely decimal
            if len(after_comma) == 2 and after_comma.isdigit():
                cleaned = cleaned.replace(',', '.')
            else:
                # Thousands separator
                cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except ValueError:
            logger.warning(f"Could not parse amount: {amount_str}")
            return None


class RevolutParser(ExpenseParser):
    """Parser specifically for Revolut transaction screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse Revolut transaction data from OCR text."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return []

        result = {'currency': 'EUR'}
        
        # Check for relative date first
        relative_date = self.detect_relative_date(text)
        if relative_date:
            logger.info(f"Revolut: Detected relative date '{relative_date}', leaving date empty")
            result['date'] = ''  # Leave empty for user to fill
            result['date_warning'] = f"Original showed '{relative_date}' - please verify date"
        
        # Extract amount - improved pattern
        amount_match = re.search(r'-?€?(\d+[.,]\d{2})', lines[0])
        if amount_match:
            result['amount'] = self.parse_european_amount(amount_match.group(1))
        else:
            # Fallback amount search in other lines
            for line in lines:
                amount_match = re.search(r'charged by merchant\s+€(\d+[.,]\d{2})', line, re.IGNORECASE)
                if amount_match:
                    result['amount'] = self.parse_european_amount(amount_match.group(1))
                    break
        
        # Extract merchant name - improved logic
        if len(lines) > 1:
            # Look for merchant name in the first few lines, skip amount line
            for i in range(1, min(4, len(lines))):
                line = lines[i].strip()
                # Skip lines that look like timestamps or other metadata
                if re.match(r'^\d{2}:\d{2}', line) or 'today' in line.lower():
                    continue
                if len(line) > 1 and not re.match(r'^[€\d\s,.-]+$', line):
                    result['description'] = self.clean_description(line)
                    break
        
        # Set default date if not relative
        if 'date' not in result:
            # Try to parse specific date formats in Revolut
            date_str = ' '.join(lines[2:4]) if len(lines) > 3 else ''
            date_match = re.search(r'(\w+\s+\d+)', date_str)
            if date_match:
                try:
                    parsed_date = datetime.strptime(
                        f"{date_match.group(1)} {datetime.now().year}", 
                        '%b %d %Y'
                    )
                    result['date'] = parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    result['date'] = datetime.now().strftime('%Y-%m-%d')
            else:
                result['date'] = datetime.now().strftime('%Y-%m-%d')
        
        # Extract category
        category_match = re.search(r'Category\s+([\w\s&]+)', text, re.IGNORECASE)
        if category_match:
            result['category'] = category_match.group(1).strip()

        # Validate essential fields
        if not result.get('amount') or not result.get('description'):
            return []

        # Set defaults for missing fields
        if 'category' not in result:
            result['category'] = self.smart_categorize(result.get('description', ''))

        return [result]


class ABNAmroSingleParser(ExpenseParser):
    """Enhanced parser for ABN AMRO single transaction screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse ABN AMRO single transaction data with improved robustness."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        full_text = '\n'.join(lines)
        amount, trx_date, description = None, None, None

        # Enhanced amount extraction with multiple strategies
        amount = self._extract_amount_robust(full_text, lines)
        
        # Extract transaction date
        trx_date = self._extract_date(full_text)
        
        # Extract and clean description
        description = self._extract_description(lines, amount, trx_date)

        # Validate and return result
        if amount is not None and description:
            cleaned_desc = self.clean_description(description)
            return [{
                'amount': amount,
                'date': trx_date or datetime.now().strftime('%Y-%m-%d'),
                'description': cleaned_desc,
                'currency': 'EUR',
                'category': self.smart_categorize(cleaned_desc)
            }]
        
        logger.warning("ABN AMRO Single parser could not find essential amount or description.")
        return []
    
    def _extract_amount_robust(self, full_text: str, lines: List[str]) -> Optional[float]:
        """Robust amount extraction with multiple strategies."""
        # Strategy 1: Look for amount near currency symbol
        amount_patterns = [
            r'€\s*(-?\d+[,.]\d{2})',  # €1.524,55 or €-6,50
            r'(-?\d+[,.]\d{2})\s*€',  # 1.524,55€ or -6,50€
            r'€\s*(-?\d+[,.]?\d*)',   # €1524 or €6
        ]
        
        for pattern in amount_patterns:
            matches = re.findall(pattern, full_text)
            if matches:
                # Take the first reasonable amount
                for match in matches:
                    amount = self.parse_european_amount(match)
                    if amount is not None and 0.01 <= abs(amount) <= 100000:
                        logger.info(f"ABN Parser: Found amount with pattern {pattern}: {amount}")
                        return amount
        
        # Strategy 2: Look for amounts in specific lines
        for line in lines:
            if any(indicator in line.lower() for indicator in ['balance', 'charged', 'your total']):
                amount_match = re.search(r'(-?\d+[,.]\d{2})', line)
                if amount_match:
                    amount = self.parse_european_amount(amount_match.group(1))
                    if amount is not None:
                        logger.info(f"ABN Parser: Found amount in context line: {amount}")
                        return amount
        
        # Strategy 3: Any reasonable amount in the text
        all_amounts = re.findall(r'(-?\d+[,.]\d{2})', full_text)
        for amount_str in all_amounts:
            amount = self.parse_european_amount(amount_str)
            if amount is not None and 0.01 <= abs(amount) <= 100000:
                logger.info(f"ABN Parser: Found fallback amount: {amount}")
                return amount
        
        logger.warning("ABN Parser: No valid amount found")
        return None
    
    def _extract_date(self, full_text: str) -> Optional[str]:
        """Extract transaction date with improved patterns."""
        # Multiple date patterns
        date_patterns = [
            r'Execution\s*\n\s*([^\n]+)',  # Original pattern
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})\s+(\w+)\s+(\d{4})',
            r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
            r'(\d{1,2})\s+(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+(\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                try:
                    if pattern == date_patterns[0]:  # Execution pattern
                        date_str = match.group(1).strip()
                        date_parts = date_str.split()
                        if len(date_parts) >= 3:
                            date_str_cleaned = " ".join(date_parts[-3:])
                            parsed_date = datetime.strptime(date_str_cleaned, '%d %B %Y')
                            result = parsed_date.strftime('%Y-%m-%d')
                            logger.info(f"ABN Parser: Found date: {result}")
                            return result
                    elif len(match.groups()) == 4:  # Day name pattern
                        day_num, month_name, year = match.group(2), match.group(3), match.group(4)
                        parsed_date = datetime.strptime(f"{day_num} {month_name} {year}", '%d %B %Y')
                        result = parsed_date.strftime('%Y-%m-%d')
                        logger.info(f"ABN Parser: Found date with day name: {result}")
                        return result
                    elif len(match.groups()) == 3:  # Month name pattern
                        day_num, month_name, year = match.groups()
                        parsed_date = datetime.strptime(f"{day_num} {month_name} {year}", '%d %B %Y')
                        result = parsed_date.strftime('%Y-%m-%d')
                        logger.info(f"ABN Parser: Found date: {result}")
                        return result
                except (ValueError, IndexError) as e:
                    logger.warning(f"Could not parse date from match '{match.group(0)}': {e}")
                    continue
        
        logger.warning("ABN Parser: Date pattern not found")
        return None
    
    def _extract_description(self, lines: List[str], amount: float, trx_date: str) -> Optional[str]:
        """Extract description by filtering out known junk patterns."""
        known_junk = [
            'payment terminal', 'execution', 'from account', 'balance after payment', 
            'description', 'google pay', 'tikkie payment request', 'share this transaction', 
            'actions', 'your total', 'charged by merchant'
        ]
        
        candidate_lines = []
        for line in lines:
            line_lower = line.lower()
            
            # Skip junk lines
            if any(junk in line_lower for junk in known_junk):
                continue
            if re.match(r'\d{2}:\d{2}', line):  # Skip time patterns
                continue
            if amount and f"{amount:.2f}".replace('.', ',') in line:  # Skip amount lines
                continue
            if trx_date:
                try:
                    date_obj = datetime.strptime(trx_date, '%Y-%m-%d')
                    if date_obj.strftime('%B').lower() in line_lower:  # Skip date lines
                        continue
                except:
                    pass
            
            # Include lines with actual content
            if re.search(r'[a-zA-Z]', line) and len(line) > 2:
                # Skip lines that are mostly numbers or symbols
                if not re.match(r'^[\d\s€,.+-]+$', line):
                    candidate_lines.append(line)

        if candidate_lines:
            # Take the first meaningful line
            description = candidate_lines[0].strip()
            logger.info(f"ABN Parser: Found description: '{description}'")
            return description
        else:
            logger.warning("ABN Parser: Could not find a suitable description line.")
            return None


class ABNAmroListParser(ExpenseParser):
    """Parser for ABN AMRO transaction list screenshots."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse ABN AMRO transaction list data from OCR text."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return []
        
        results = []
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Find the date for the whole list
        for line in lines:
            try:
                # Format "Thursday 29 May 2025"
                parsed_date = datetime.strptime(line, '%A %d %B %Y')
                current_date = parsed_date.strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
        
        # Process transaction lines
        for line in lines:
            # Regex to find description and amount on the same line
            match = re.match(r'(.+?)\s+-\s*(\d+,\d{2})$', line)
            if match:
                description = match.group(1).strip()
                amount_str = match.group(2)
                amount = self.parse_european_amount(amount_str)
                
                # Avoid matching the date line as a transaction
                weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                if description.lower() not in weekdays and amount is not None:
                    cleaned_desc = self.clean_description(description)
                    results.append({
                        'description': cleaned_desc,
                        'amount': amount,
                        'date': current_date,
                        'currency': 'EUR',
                        'category': self.smart_categorize(cleaned_desc)
                    })
        
        return results


class GenericParser(ExpenseParser):
    """Fallback parser for unknown receipt types."""
    
    def parse(self, text: str) -> List[Dict[str, Any]]:
        """Parse generic receipt data from OCR text."""
        # Look for total amount
        amount_match = re.search(r'(?:total|totaal|amount|bedrag)[:\s]+(\d+[,.]\d{2})', text, re.IGNORECASE)
        if amount_match:
            amount = self.parse_european_amount(amount_match.group(1))
        else:
            # Look for standalone amounts and pick the largest
            amounts = re.findall(r'(\d+[.,]\d{2})', text)
            if amounts:
                parsed_amounts = [self.parse_european_amount(a) for a in amounts]
                valid_amounts = [a for a in parsed_amounts if a is not None]
                amount = max(valid_amounts) if valid_amounts else 0.0
            else:
                amount = 0.0

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        description = lines[0] if lines else 'Scanned Expense'
        
        # Extract date
        current_date = datetime.now().strftime('%Y-%m-%d')
        date_match = re.search(r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', text)
        if date_match:
            try:
                d_str = date_match.group(1).replace('-', '/')
                parsed_date = datetime.strptime(d_str, '%d/%m/%Y')
                current_date = parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                pass  # Use current date if parsing fails

        # Validate that we have meaningful data
        if amount == 0.0 and description == 'Scanned Expense':
            return []

        cleaned_desc = self.clean_description(description)
        return [{
            'amount': amount,
            'currency': 'EUR',
            'date': current_date,
            'description': cleaned_desc,
            'category': self.smart_categorize(cleaned_desc)
        }]