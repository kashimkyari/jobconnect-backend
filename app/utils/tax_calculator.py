from decimal import Decimal
from datetime import datetime
from typing import Dict, Tuple
import re


class TaxCalculator:
    """Nigerian tax calculation for marketplace transactions"""
    
    # Tax rates (percentage)
    VAT_RATE = 0.075  # 7.5%
    WHT_RATE = 0.05   # 5% Withholding Tax
    
    # Invoice numbering
    INVOICE_PREFIX = "INV"
    
    @staticmethod
    def calculate_vat(amount: float, is_exempt: bool = False) -> float:
        """Calculate VAT (7.5%) on amount, returns 0 if exempt"""
        if is_exempt:
            return 0.0
        return round(amount * TaxCalculator.VAT_RATE, 2)
    
    @staticmethod
    def calculate_wht(amount: float, user_type: str) -> float:
        """
        Calculate WHT (5%) on amount
        Only applies to workers, not employers
        """
        if user_type.lower() not in ['worker', 'freelancer', 'provider']:
            return 0.0
        return round(amount * TaxCalculator.WHT_RATE, 2)
    
    @staticmethod
    def generate_invoice_number(user_id: int, transaction_date: datetime = None) -> str:
        """
        Generate sequential invoice number by date
        Format: INV-20260206-{sequence}
        """
        if transaction_date is None:
            transaction_date = datetime.now()
        
        date_str = transaction_date.strftime("%Y%m%d")
        # Use user_id mod 10000 for sequence
        sequence = str(user_id % 10000).zfill(5)
        
        return f"{TaxCalculator.INVOICE_PREFIX}-{date_str}-{sequence}"
    
    @staticmethod
    def calculate_payment_breakdown(
        gross_amount: float,
        user_type: str,
        is_tax_exempt: bool = False,
        include_platform_fee: bool = True
    ) -> Dict[str, float]:
        """
        Calculate complete payment breakdown
        
        Example for employer funding wallet (gross_amount = 10,000):
        {
            'base_amount': 10000.00,
            'vat_amount': 750.00,
            'vat_rate': 0.075,
            'platform_fee': 0.00,
            'total_payable': 10750.00,
            'invoice_number': 'INV-20260206-00001'
        }
        
        Example for worker payment (gross_amount = 5,000):
        {
            'base_amount': 5000.00,
            'vat_amount': 375.00,
            'wht_amount': 236.88,
            'total_payable': 5375.00,
            'worker_receives': 5138.12,
            'invoice_number': 'INV-20260206-00001'
        }
        """
        breakdown = {
            'base_amount': gross_amount,
            'vat_rate': TaxCalculator.VAT_RATE,
            'wht_rate': TaxCalculator.WHT_RATE,
            'user_type': user_type,
            'is_tax_exempt': is_tax_exempt,
        }
        
        # Calculate VAT
        vat_amount = TaxCalculator.calculate_vat(gross_amount, is_tax_exempt)
        breakdown['vat_amount'] = vat_amount
        
        # Subtotal after VAT
        subtotal_with_vat = gross_amount + vat_amount
        breakdown['subtotal_with_vat'] = subtotal_with_vat
        
        # Calculate WHT (only for workers/providers receiving payments)
        if user_type.lower() in ['worker', 'freelancer', 'provider']:
            # WHT calculated on the gross amount before VAT addition
            wht_amount = TaxCalculator.calculate_wht(gross_amount, user_type)
            breakdown['wht_amount'] = wht_amount
            breakdown['worker_receives'] = subtotal_with_vat - wht_amount
            breakdown['total_payable'] = subtotal_with_vat
        else:
            # Employer - no WHT
            breakdown['wht_amount'] = 0.0
            breakdown['total_payable'] = subtotal_with_vat
        
        # Generate invoice
        breakdown['invoice_number'] = TaxCalculator.generate_invoice_number(int(gross_amount * 1000) % 10000)
        
        return breakdown
    
    @staticmethod
    def validate_tin(tin: str) -> bool:
        """
        Validate Nigerian TIN (Tax Identification Number)
        Format: 11 digits
        """
        if not tin:
            return False
        # Remove hyphens if present
        tin_cleaned = tin.replace('-', '')
        # Check if it's 11 digits
        return bool(re.match(r'^\d{11}$', tin_cleaned))
    
    @staticmethod
    def validate_bvn(bvn: str) -> bool:
        """
        Validate Nigerian BVN (Bank Verification Number)
        Format: 11 digits
        """
        if not bvn:
            return False
        bvn_cleaned = bvn.replace('-', '')
        return bool(re.match(r'^\d{11}$', bvn_cleaned))
