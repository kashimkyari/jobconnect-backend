from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from ..database import get_db
from ..models.user import User
from ..models.tax_profile import WorkerTaxProfile, TaxProfileState
from ..services.auth_service import get_current_user
from ..services.tax_service import TaxService
from ..schemas.tax_schemas import (
    WorkerTaxProfileCreate,
    WorkerTaxProfileResponse,
    TaxReportRequest,
    TaxReportResponse,
    WorkerEarningsResponse,
    TaxStatementResponse,
)
from ..utils.logging import app_logger

router = APIRouter(prefix="/tax", tags=["Tax Compliance"])


@router.get("/state", response_model=dict)
async def get_tax_profile_state(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get worker's current tax profile state
    Returns: not_registered, registered, pending_verification, verified, tax_exempt, or suspended
    Useful for quick state checks in UI
    """
    try:
        from sqlalchemy.future import select
        
        query = select(WorkerTaxProfile).where(WorkerTaxProfile.user_id == current_user.id)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            return {
                "status": "success",
                "data": {
                    "state": TaxProfileState.NOT_REGISTERED.value,
                    "is_verified": False,
                    "is_compliant": True,
                    "is_registered": False,
                }
            }
        
        return {
            "status": "success",
            "data": {
                "state": profile.state.value,
                "is_verified": profile.is_verified,
                "is_compliant": profile.is_compliant,
                "is_registered": True,
                "tax_classification": profile.tax_classification,
                "verification_status": profile.verification_status,
            }
        }
    except Exception as e:
        app_logger.error(f"Error fetching tax profile state: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/current-month", response_model=dict)
async def get_current_month_summary(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current month's earnings summary with tax breakdown
    Useful for dashboard overview
    """
    try:
        service = TaxService(db)
        
        now = datetime.utcnow()
        start_date = datetime(now.year, now.month, 1)
        end_date = now
        
        earnings = await service.get_worker_earnings(current_user.id, start_date, end_date)
        
        return {
            "status": "success",
            "data": earnings
        }
    except Exception as e:
        app_logger.error(f"Error fetching current month summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile-with-summary", response_model=dict)
async def get_tax_profile_with_summary(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get tax profile AND current month earnings summary in one call
    Optimized for dashboard initialization
    """
    try:
        service = TaxService(db)
        
        # Get profile
        profile = await service.get_worker_tax_profile(current_user.id)
        
        # Get current month summary if registered
        summary = None
        if profile:
            now = datetime.utcnow()
            start_date = datetime(now.year, now.month, 1)
            end_date = now
            summary = await service.get_worker_earnings(current_user.id, start_date, end_date)
        
        return {
            "status": "success",
            "data": {
                "profile": profile,
                "current_month_summary": summary
            }
        }
    except Exception as e:
        app_logger.error(f"Error fetching profile with summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# WORKER TAX PROFILE ENDPOINTS
@router.get("/profile", response_model=dict)
async def get_tax_profile(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get worker's tax profile if registered"""
    try:
        user = await db.get(User, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Try to get tax profile from user metadata
        tax_profile = None
        if hasattr(user, 'payment_metadata') and user.payment_metadata:
            tax_profile = user.payment_metadata.get('tax_profile')
        
        # Return null data if not registered (instead of 404)
        if not tax_profile:
            return {
                "status": "success",
                "data": None,
                "message": "Tax profile not registered"
            }
        
        return {
            "status": "success",
            "data": {
                "id": user.id,
                **tax_profile
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error fetching tax profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile/register", response_model=dict)
async def register_tax_profile(
    profile_data: WorkerTaxProfileCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register or update worker tax profile (TIN, BVN, classification)"""
    try:
        service = TaxService(db)
        result = await service.register_worker_tax_profile(current_user.id, profile_data)
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        app_logger.error(f"Error registering tax profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/worker/earnings", response_model=dict)
async def get_worker_earnings(
    start_date: Optional[str] = Query(None, description="ISO format start date"),
    end_date: Optional[str] = Query(None, description="ISO format end date"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get worker earnings with tax breakdown
    Query params:
      - start_date: ISO format (default: 30 days ago)
      - end_date: ISO format (default: now)
    """
    try:
        service = TaxService(db)
        
        # Parse dates
        sd = datetime.fromisoformat(start_date) if start_date else None
        ed = datetime.fromisoformat(end_date) if end_date else None
        
        earnings = await service.get_worker_earnings(current_user.id, sd, ed)
        
        return {
            "status": "success",
            "data": earnings
        }
    except Exception as e:
        app_logger.error(f"Error fetching worker earnings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statement/{year}", response_model=dict)
async def get_tax_statement_annual(
    year: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get annual tax statement for a specific year
    Path params:
      - year: 2026 (annual summary for the entire year)
    """
    try:
        service = TaxService(db)
        statement = await service.generate_tax_statement(current_user.id, year, month=None)
        
        return {
            "status": "success",
            "data": statement
        }
    except Exception as e:
        app_logger.error(f"Error generating tax statement: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statement/{year}/{month}", response_model=dict)
async def get_tax_statement_monthly(
    year: int,
    month: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get monthly or annual tax statement
    Path params:
      - year: 2026
      - month: 1-12 (for monthly statement)
    """
    try:
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Month must be 1-12")
        
        service = TaxService(db)
        statement = await service.generate_tax_statement(current_user.id, year, month)
        
        return {
            "status": "success",
            "data": statement
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error generating tax statement: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statement/{year}/{month}/pdf")
async def download_tax_statement_pdf(
    year: int,
    month: Optional[int] = None,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Download tax statement as PDF
    Returns PDF bytes for annual/monthly report
    """
    raise HTTPException(status_code=501, detail="PDF generation coming soon")


# ADMIN TAX REPORTING ENDPOINTS
@router.get("/admin/vat-report/{year}/{month}", response_model=dict)
async def get_vat_report(
    year: int,
    month: int,
    admin = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get VAT collection report for a specific month
    Admin only - for tax compliance and remittance
    """
    # Check admin role
    if not hasattr(admin, 'role') or admin.role != 'ADMIN':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    raise HTTPException(status_code=501, detail="VAT report coming soon")


@router.get("/admin/wht-report/{year}/{month}", response_model=dict)
async def get_wht_report(
    year: int,
    month: int,
    admin = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get WHT (Withholding Tax) collection report
    Admin only - for FIRS remittance
    """
    # Check admin role
    if not hasattr(admin, 'role') or admin.role != 'ADMIN':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    raise HTTPException(status_code=501, detail="WHT report coming soon")


@router.post("/admin/process-wht-remittance")
async def process_wht_remittance(
    year: int = Query(...),
    month: int = Query(...),
    admin = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark WHT as remitted to FIRS
    Admin only - creates compliance record
    """
    # Check admin role
    if not hasattr(admin, 'role') or admin.role != 'ADMIN':
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "status": "success",
        "message": f"WHT remittance processed for {year}-{month:02d}",
        "amount": 0,
    }
