"""
Service for handling tax calculations specific to withdrawal requests.
Tax preferences: BEFORE (add tax on-top) or AFTER (deduct tax from amount)
"""
from decimal import Decimal
from typing import Dict, Tuple
from fastapi import HTTPException, status
import logging

from app.models.enums import TaxPreference

logger = logging.getLogger(__name__)


class TaxWithdrawalService:
    """Service for calculating withdrawal taxes based on user preference"""
    
    # Standard tax rate for withdrawals (can be configured globally)
    WITHDRAWAL_TAX_RATE = Decimal("0.10")  # 10%
    
    @staticmethod
    def calculate_withdrawal_tax(
        amount: Decimal,
        tax_preference: TaxPreference,
        tax_rate: Decimal = None
    ) -> Dict[str, Decimal]:
        """
        Calculate withdrawal tax based on user preference.
        
        Args:
            amount: The withdrawal amount (decimal)
            tax_preference: TaxPreference.BEFORE or TaxPreference.AFTER
            tax_rate: Override default tax rate (defaults to 10%)
        
        Returns:
            Dict with keys:
            - tax_amount: Amount of tax to be deducted
            - net_amount: Amount user receives (after tax if AFTER mode)
            - charge_amount: Total amount to deduct from wallet
            - user_receives: Final amount in user's bank account
            - mode: BEFORE or AFTER
        
        Examples:
            BEFORE mode (user pays tax ON TOP):
                amount = 100,000, tax_rate = 10%
                → tax_amount = 10,000
                → charge_amount = 110,000 (deduct from wallet)
                → user_receives = 100,000 (to bank)
            
            AFTER mode (tax deducted FROM requested amount):
                amount = 100,000, tax_rate = 10%
                → charge_amount = 111,111 (to get 100,000 after tax)
                → tax_amount = 11,111
                → user_receives = 100,000 (to bank)
        """
        if not tax_rate:
            tax_rate = TaxWithdrawalService.WITHDRAWAL_TAX_RATE
        
        # Validate inputs
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Withdrawal amount must be greater than 0"
            )
        
        if tax_rate < 0 or tax_rate > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tax rate must be between 0 and 1"
            )
        
        # Ensure we're working with Decimal for precision
        amount = Decimal(str(amount))
        tax_rate = Decimal(str(tax_rate))
        
        if tax_preference == TaxPreference.BEFORE:
            # User wants to receive 'amount', we add tax on top
            tax_amount = amount * tax_rate
            charge_amount = amount + tax_amount
            user_receives = amount
            
        elif tax_preference == TaxPreference.AFTER:
            # User specified amount after considering tax deduction
            # We need to calculate: charge_amount such that
            # user_receives = charge_amount - (charge_amount * tax_rate) = amount
            # charge_amount * (1 - tax_rate) = amount
            # charge_amount = amount / (1 - tax_rate)
            one_minus_rate = Decimal("1") - tax_rate
            if one_minus_rate <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tax rate is too high"
                )
            charge_amount = amount / one_minus_rate
            tax_amount = charge_amount - amount
            user_receives = amount
            
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tax preference"
            )
        
        # Round to 2 decimal places (NGN)
        return {
            "tax_amount": tax_amount.quantize(Decimal("0.01")),
            "net_amount": amount,
            "charge_amount": charge_amount.quantize(Decimal("0.01")),
            "user_receives": user_receives.quantize(Decimal("0.01")),
            "mode": tax_preference.value,
            "tax_rate": float(tax_rate) * 100,  # As percentage for display
        }
    
    @staticmethod
    def validate_sufficient_balance(
        wallet_balance: Decimal,
        charge_amount: Decimal
    ) -> bool:
        """
        Validate that wallet has sufficient balance for withdrawal.
        
        Args:
            wallet_balance: Current wallet balance
            charge_amount: Total amount to be deducted (amount + tax)
        
        Returns:
            True if sufficient balance, raises exception otherwise
        """
        wallet_balance = Decimal(str(wallet_balance))
        charge_amount = Decimal(str(charge_amount))
        
        if wallet_balance < charge_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient wallet balance. Required: {charge_amount}, Available: {wallet_balance}"
            )
        
        return True
    
    @staticmethod
    def format_currency(amount: Decimal, currency: str = "NGN") -> str:
        """Format amount as currency string for display"""
        return f"{currency} {amount:,.2f}"
