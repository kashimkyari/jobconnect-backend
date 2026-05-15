from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func
from fastapi import HTTPException, status
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging

from ..models.user import User
from ..models.transaction import Transaction, TransactionType
from ..models.tax_profile import WorkerTaxProfile, TaxProfileState
from ..utils.tax_calculator import TaxCalculator
from ..schemas.tax_schemas import WorkerTaxProfileCreate

logger = logging.getLogger(__name__)


class TaxService:
    """Service for handling tax calculations, reporting, and compliance"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tax_calculator = TaxCalculator()
    
    async def register_worker_tax_profile(
        self,
        user_id: int,
        tax_profile_data: WorkerTaxProfileCreate
    ) -> Dict:
        """
        Register or update worker tax profile
        Creates WorkerTaxProfile database record with initial REGISTERED state
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Validate TIN format
        if not TaxCalculator.validate_tin(tax_profile_data.tin):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid TIN format. Must be 11 digits."
            )
        
        # Validate BVN if provided
        if tax_profile_data.bvn and not TaxCalculator.validate_bvn(tax_profile_data.bvn):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid BVN format. Must be 11 digits."
            )
        
        # Check if tax profile already exists
        query = select(WorkerTaxProfile).where(WorkerTaxProfile.user_id == user_id)
        result = await self.db.execute(query)
        existing_profile = result.scalar_one_or_none()
        
        if existing_profile:
            # Update existing profile
            existing_profile.tin = tax_profile_data.tin
            existing_profile.bvn = tax_profile_data.bvn
            existing_profile.tax_classification = tax_profile_data.tax_classification
            existing_profile.state = TaxProfileState.REGISTERED
            await self.db.merge(existing_profile)
        else:
            # Create new profile
            tax_profile = WorkerTaxProfile(
                user_id=user_id,
                tin=tax_profile_data.tin,
                bvn=tax_profile_data.bvn,
                tax_classification=tax_profile_data.tax_classification,
                state=TaxProfileState.REGISTERED,
                is_verified=False,
                is_tax_exempt=False,
            )
            self.db.add(tax_profile)
        
        await self.db.commit()
        
        logger.info(
            f"Tax profile registered for user {user_id}",
            extra={"user_id": user_id, "classification": tax_profile_data.tax_classification}
        )
        
        return {
            "user_id": user_id,
            "tin": tax_profile_data.tin,
            "bvn": tax_profile_data.bvn,
            "tax_classification": tax_profile_data.tax_classification,
            "state": TaxProfileState.REGISTERED.value,
            "is_verified": False,
            "is_tax_exempt": False,
            "created_at": datetime.utcnow(),
        }
    
    async def get_worker_tax_profile(
        self,
        user_id: int
    ) -> Optional[Dict]:
        """
        Retrieve worker's tax profile with state
        Returns None if not registered
        """
        query = select(WorkerTaxProfile).where(WorkerTaxProfile.user_id == user_id)
        result = await self.db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            return None
        
        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "tin": profile.tin,
            "bvn": profile.bvn,
            "tax_classification": profile.tax_classification,
            "state": profile.state.value,
            "is_verified": profile.is_verified,
            "is_tax_exempt": profile.is_tax_exempt,
            "verification_status": profile.verification_status,
            "is_compliant": profile.is_compliant,
            "registered_at": profile.registered_at.isoformat() if profile.registered_at else None,
            "verified_at": profile.verified_at.isoformat() if profile.verified_at else None,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
    
    async def get_worker_earnings(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get worker earnings summary with tax breakdown
        Returns gross, VAT, WHT, and net earnings
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Query transactions for this user in the period
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date,
                Transaction.created_at <= end_date,
                Transaction.transaction_type == TransactionType.ESCROW_RELEASE
            )
        )
        
        result = await self.db.execute(query)
        transactions = result.scalars().all()
        
        # Calculate totals
        total_gross = Decimal("0")
        total_vat = Decimal("0")
        total_wht = Decimal("0")
        
        for txn in transactions:
            amount = txn.amount or Decimal("0")
            total_gross += amount
            
            # Tax details would be stored in txn metadata
            if hasattr(txn, 'metadata') and txn.metadata:
                vat_amt = txn.metadata.get('vat_amount', 0)
                wht_amt = txn.metadata.get('wht_amount', 0)
                if vat_amt:
                    total_vat += Decimal(str(vat_amt))
                if wht_amt:
                    total_wht += Decimal(str(wht_amt))
        
        net_earnings = total_gross - total_vat - total_wht
        
        return {
            "total_earnings": float(total_gross),
            "vat_amount": float(total_vat),
            "wht_amount": float(total_wht),
            "net_amount": float(net_earnings),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "transaction_count": len(transactions),
            "currency": "NGN",
        }
    
    async def generate_tax_statement(
        self,
        user_id: int,
        year: int,
        month: Optional[int] = None
    ) -> Dict:
        """
        Generate monthly or annual tax statement
        Aggregates transactions with tax breakdown
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Set date range
        if month:
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)
            period = f"{year:04d}-{month:02d}"
            statement_type = "monthly"
        else:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)
            period = f"{year:04d}"
            statement_type = "annual"
        
        # Query transactions
        query = select(Transaction).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date,
                Transaction.created_at < end_date,
                Transaction.transaction_type.in_([
                    TransactionType.ESCROW_RELEASE,
                    TransactionType.WALLET_WITHDRAWAL
                ])
            )
        )
        
        result = await self.db.execute(query)
        transactions = result.scalars().all()
        
        # Aggregate
        total_gross = Decimal("0")
        total_vat = Decimal("0")
        total_wht = Decimal("0")
        
        for txn in transactions:
            amount = txn.amount or Decimal("0")
            total_gross += amount
            
            if hasattr(txn, 'metadata') and txn.metadata:
                vat_amt = txn.metadata.get('vat_amount', 0)
                wht_amt = txn.metadata.get('wht_amount', 0)
                if vat_amt:
                    total_vat += Decimal(str(vat_amt))
                if wht_amt:
                    total_wht += Decimal(str(wht_amt))
        
        net_amount = total_gross - total_vat - total_wht
        
        statement = {
            "statement_id": f"TAX-{user_id}-{period}",
            "user_id": user_id,
            "period": period,
            "statement_type": statement_type,
            "transactions_count": len(transactions),
            "vat_collected": float(total_vat),
            "vat_remitted": None,
            "wht_deducted": float(total_wht),
            "total_gross_volume": float(total_gross),
            "net_amount_paid": float(net_amount),
            "generated_at": datetime.utcnow().isoformat(),
            "status": "draft",
        }
        
        return statement
    
    async def calculate_monthly_wht_payable(self) -> Dict:
        """
        Calculate total WHT collected across all workers for FIRS remittance
        Called monthly for tax compliance reporting
        """
        # Query all WHT transactions from current month
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        
        if now.month == 12:
            end_of_month = datetime(now.year + 1, 1, 1)
        else:
            end_of_month = datetime(now.year, now.month + 1, 1)
        
        query = select(func.sum(Transaction.platform_fee)).where(
            and_(
                Transaction.created_at >= start_of_month,
                Transaction.created_at < end_of_month,
                Transaction.transaction_type == TransactionType.ESCROW_RELEASE
            )
        )
        
        result = await self.db.execute(query)
        total_wht_collected = result.scalar() or Decimal("0")
        
        return {
            "period": f"{now.year:04d}-{now.month:02d}",
            "total_wht_collected": float(total_wht_collected),
            "status": "pending_remittance",
            "remittance_due_date": (end_of_month + timedelta(days=14)).isoformat(),
            "currency": "NGN",
        }
