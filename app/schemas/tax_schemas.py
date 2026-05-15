from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List
from decimal import Decimal
from datetime import datetime
from enum import Enum


class TaxClassification(str, Enum):
    """Tax classification for businesses"""
    INDIVIDUAL = "individual"
    LIMITED_COMPANY = "limited_company"
    PARTNERSHIP = "partnership"
    SELF_EMPLOYED = "self_employed"


class TaxProfileState(str, Enum):
    """Tax profile states"""
    NOT_REGISTERED = "not_registered"
    REGISTERED = "registered"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    TAX_EXEMPT = "tax_exempt"
    SUSPENDED = "suspended"


class WorkerTaxProfileCreate(BaseModel):
    """Create/Register worker tax profile"""
    tin: str = Field(..., description="Tax Identification Number (11 digits)")
    bvn: Optional[str] = Field(None, description="Bank Verification Number (11 digits)")
    tax_classification: TaxClassification = Field(TaxClassification.INDIVIDUAL)
    
    @field_validator('tin')
    @classmethod
    def validate_tin(cls, v):
        if not v or len(v.replace('-', '')) != 11:
            raise ValueError('TIN must be 11 digits')
        return v
    
    @field_validator('bvn')
    @classmethod
    def validate_bvn(cls, v):
        if v and len(v.replace('-', '')) != 11:
            raise ValueError('BVN must be 11 digits if provided')
        return v


class WorkerTaxProfileResponse(BaseModel):
    """Worker tax profile response"""
    user_id: int
    tin: str
    bvn: Optional[str]
    tax_classification: TaxClassification
    state: TaxProfileState = TaxProfileState.REGISTERED
    is_verified: bool = False
    is_tax_exempt: bool = False
    verification_status: str = "pending"
    is_compliant: bool = True
    registered_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class PaymentTaxBreakdown(BaseModel):
    """Tax breakdown for a payment"""
    base_amount: Decimal
    vat_amount: Decimal
    vat_rate: float = 0.075
    platform_fee: Decimal = Decimal("0")
    wht_amount: Optional[Decimal] = None
    wht_rate: float = 0.05
    net_amount: Decimal
    invoice_number: str
    user_type: str


class PaymentWithTaxResponse(BaseModel):
    """Payment response with tax details"""
    transaction_id: str
    amount: Decimal
    tax_breakdown: PaymentTaxBreakdown
    invoice_number: str
    paid_at: datetime
    
    class Config:
        from_attributes = True


class WorkerEarningsResponse(BaseModel):
    """Worker earnings summary"""
    total_gross: float
    total_vat: float
    total_wht: float
    net_earnings: float
    period_start: str
    period_end: str
    transaction_count: int
    currency: str = "NGN"
    
    class Config:
        from_attributes = True


class TaxStatementResponse(BaseModel):
    """Annual/Monthly tax statement"""
    statement_id: str
    user_id: int
    period: str  # "2026-02" or "2026"
    statement_type: str  # "monthly" or "annual"
    transactions_count: int
    vat_collected: float
    vat_remitted: Optional[float] = None
    wht_deducted: float
    total_gross_volume: float
    net_amount_paid: float
    generated_at: str
    status: str  # "draft", "filed", "approved"
    
    class Config:
        from_attributes = True


class TaxReportRequest(BaseModel):
    """Request for admin tax reports"""
    year: int
    month: Optional[int] = None
    report_type: str = "both"  # "vat", "wht", "both"


class TaxReportResponse(BaseModel):
    """Admin tax report response"""
    report_type: str
    period: str
    total_transactions: int
    total_amount: float
    vat_collected: Optional[float] = None
    wht_collected: Optional[float] = None
    remittance_status: str  # "pending", "remitted", "verified"
    generated_at: str
    
    class Config:
        from_attributes = True
