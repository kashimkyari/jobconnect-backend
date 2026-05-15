"""
Admin endpoints for withdrawal request management and approval.
Allows admins to view, approve, and decline user withdrawal requests.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from decimal import Decimal

from app.models.user import User, UserRole
from app.models.enums import WithdrawalRequestStatus
from app.models.dispute import Dispute, DisputeStatus
from app.services.auth_service import get_current_user, get_admin_user
from app.services.withdrawal_service import WithdrawalService
from app.database import get_db
from app.utils.logging import payment_logger

router = APIRouter(prefix="/admin/withdrawals", tags=["admin-withdrawals"])


@router.get("/requests", response_model=Dict[str, Any])
async def list_withdrawal_requests(
    status_filter: Optional[WithdrawalRequestStatus] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all withdrawal requests with optional status filtering.
    Admin only endpoint.
    """
    from sqlalchemy.future import select
    from sqlalchemy import desc, func
    from sqlalchemy.orm import selectinload
    from app.models.withdrawal_request import WithdrawalRequest
    
    try:
        query = select(WithdrawalRequest).options(
            selectinload(WithdrawalRequest.user),
            selectinload(WithdrawalRequest.bank_account),
        )
        
        if status_filter:
            query = query.where(WithdrawalRequest.status == status_filter)
        
        # Get total count
        count_query = select(func.count(WithdrawalRequest.id))
        if status_filter:
            count_query = count_query.where(WithdrawalRequest.status == status_filter)
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Get paginated results
        query = query.order_by(desc(WithdrawalRequest.created_at)).limit(limit).offset(offset)
        result = await db.execute(query)
        requests = result.scalars().all()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "requests": [
                {
                    "id": req.id,
                    "user": {
                        "id": req.user.id,
                        "email": req.user.email,
                        "first_name": req.user.first_name,
                        "last_name": req.user.last_name
                    },
                    "amount": float(req.amount),
                    "tax_amount": float(req.tax_amount),
                    "total_amount": float(req.total_amount),
                    "tax_preference": req.tax_preference.value,
                    "status": req.status.value,
                    "bank_account": {
                        "account_name": req.bank_account.account_name,
                        "account_number": req.bank_account.account_number,
                        "bank_name": req.bank_account.bank_name
                    },
                    "created_at": req.created_at.isoformat(),
                    "approved_at": req.approved_at.isoformat() if req.approved_at else None
                }
                for req in requests
            ]
        }
    except Exception as e:
        payment_logger.error(f"Error listing withdrawal requests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list withdrawal requests"
        )


@router.get("/requests/{request_id}", response_model=Dict[str, Any])
async def get_withdrawal_request(
    request_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific withdrawal request.
    Admin only endpoint.
    """
    try:
        withdrawal_service = WithdrawalService(db)
        request_details = await withdrawal_service.get_withdrawal_request(request_id)
        return request_details
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error fetching withdrawal request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch withdrawal request"
        )


@router.post("/requests/{request_id}/approve", response_model=Dict[str, Any])
async def approve_withdrawal_request(
    request_id: int,
    notes: Optional[str] = None,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin approves a withdrawal request and initiates Paystack transfer.
    Admin only endpoint.
    
    This will:
    1. Verify the request is in PENDING status
    2. Create transfer recipient with bank account details
    3. Initiate Paystack transfer for the withdrawal amount
    4. Create Payment record linked to withdrawal request
    5. Update withdrawal request status to APPROVED
    6. Send notification to user
    """
    try:
        withdrawal_service = WithdrawalService(db)
        result = await withdrawal_service.approve_withdrawal_request(
            request_id=request_id,
            admin_id=current_user.id,
            notes=notes
        )
        
        payment_logger.info(
            f"Withdrawal request {request_id} approved by admin {current_user.id}"
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error approving withdrawal request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve withdrawal request"
        )


@router.post("/requests/{request_id}/decline", response_model=Dict[str, Any])
async def decline_withdrawal_request(
    request_id: int,
    reason: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin declines a withdrawal request and restores funds to user's wallet.
    Admin only endpoint.
    
    This will:
    1. Verify the request is in PENDING status
    2. Restore total_amount (amount + tax) back to user's wallet
    3. Update withdrawal request status to DECLINED
    4. Record admin notes and decline reason
    5. Send notification to user
    """
    if not reason or len(reason.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decline reason is required"
        )
    
    try:
        withdrawal_service = WithdrawalService(db)
        result = await withdrawal_service.decline_withdrawal_request(
            request_id=request_id,
            admin_id=current_user.id,
            reason=reason
        )
        
        payment_logger.info(
            f"Withdrawal request {request_id} declined by admin {current_user.id}: {reason}"
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error declining withdrawal request {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decline withdrawal request"
        )


@router.get("/stats", response_model=Dict[str, Any])
async def get_withdrawal_stats(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get withdrawal statistics (pending count, total amount pending, etc).
    Admin only endpoint.
    """
    try:
        from sqlalchemy.future import select
        from sqlalchemy import func
        from app.models.withdrawal_request import WithdrawalRequest
        
        # Count pending requests
        pending_result = await db.execute(
            select(func.count(WithdrawalRequest.id)).where(
                WithdrawalRequest.status == WithdrawalRequestStatus.PENDING
            )
        )
        pending_count = pending_result.scalar() or 0
        
        # Sum pending amounts
        pending_amount_result = await db.execute(
            select(func.sum(WithdrawalRequest.amount)).where(
                WithdrawalRequest.status == WithdrawalRequestStatus.PENDING
            )
        )
        pending_amount = pending_amount_result.scalar() or Decimal("0.0")
        
        # Count approved requests
        approved_result = await db.execute(
            select(func.count(WithdrawalRequest.id)).where(
                WithdrawalRequest.status == WithdrawalRequestStatus.APPROVED
            )
        )
        approved_count = approved_result.scalar() or 0
        
        # Count declined requests
        declined_result = await db.execute(
            select(func.count(WithdrawalRequest.id)).where(
                WithdrawalRequest.status == WithdrawalRequestStatus.DECLINED
            )
        )
        declined_count = declined_result.scalar() or 0
        
        return {
            "pending_count": pending_count,
            "pending_amount": float(pending_amount),
            "approved_count": approved_count,
            "declined_count": declined_count
        }
    except Exception as e:
        payment_logger.error(f"Error fetching withdrawal stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch withdrawal statistics"
        )


# ========================
# WITHDRAWAL DISPUTE ENDPOINTS
# ========================

@router.get("/disputes", response_model=Dict[str, Any])
async def list_withdrawal_disputes(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all withdrawal-related disputes.
    Admin only endpoint.
    
    Filters:
    - status_filter: open, under_review, resolved
    """
    from sqlalchemy.future import select
    from sqlalchemy import desc, and_
    from app.models.dispute import DisputeType
    
    try:
        # Build query for withdrawal disputes
        query = select(Dispute).where(Dispute.dispute_type == DisputeType.WITHDRAWAL)
        
        if status_filter:
            try:
                status_enum = DisputeStatus(status_filter.lower())
                query = query.where(Dispute.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid status filter. Must be: open, under_review, resolved"
                )
        
        # Count total
        count_query = select(Dispute).where(Dispute.dispute_type == DisputeType.WITHDRAWAL)
        if status_filter:
            count_query = count_query.where(Dispute.status == status_enum)
        
        count_result = await db.execute(
            count_query.with_only_columns(__import__('sqlalchemy').func.count(Dispute.id))
        )
        total = count_result.scalar() or 0
        
        # Get paginated results
        query = query.order_by(desc(Dispute.created_at)).limit(limit).offset(offset)
        result = await db.execute(query)
        disputes = result.scalars().all()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "disputes": [
                {
                    "id": dispute.id,
                    "withdrawal_request_id": dispute.withdrawal_request_id,
                    "user": {
                        "id": dispute.affected_user.id,
                        "email": dispute.affected_user.email,
                        "first_name": dispute.affected_user.first_name,
                        "last_name": dispute.affected_user.last_name
                    },
                    "reason": dispute.reason,
                    "status": dispute.status.value,
                    "resolution": dispute.resolution,
                    "resolution_action": dispute.resolution_action,
                    "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
                    "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None
                }
                for dispute in disputes
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error listing withdrawal disputes: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list withdrawal disputes"
        )


@router.get("/disputes/{dispute_id}", response_model=Dict[str, Any])
async def get_withdrawal_dispute(
    dispute_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific withdrawal dispute.
    Admin only endpoint.
    """
    from sqlalchemy.future import select
    
    try:
        result = await db.execute(
            select(Dispute).where(
                (Dispute.id == dispute_id) & 
                (Dispute.dispute_type == "withdrawal")
            )
        )
        dispute = result.scalar()
        
        if not dispute:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal dispute not found"
            )
        
        withdrawal_req = dispute.withdrawal_request
        
        return {
            "id": dispute.id,
            "dispute_type": dispute.dispute_type.value,
            "withdrawal_request": {
                "id": withdrawal_req.id,
                "amount": float(withdrawal_req.amount),
                "tax_amount": float(withdrawal_req.tax_amount),
                "total_amount": float(withdrawal_req.total_amount),
                "status": withdrawal_req.status.value,
                "created_at": withdrawal_req.created_at.isoformat()
            },
            "user": {
                "id": dispute.affected_user.id,
                "email": dispute.affected_user.email,
                "first_name": dispute.affected_user.first_name,
                "last_name": dispute.affected_user.last_name,
                "wallet_balance": float(dispute.affected_user.wallet_balance)
            },
            "reason": dispute.reason,
            "status": dispute.status.value,
            "resolution": dispute.resolution,
            "resolution_action": dispute.resolution_action,
            "resolved_by_admin": {
                "id": dispute.resolved_by_admin.id,
                "email": dispute.resolved_by_admin.email,
                "first_name": dispute.resolved_by_admin.first_name,
                "last_name": dispute.resolved_by_admin.last_name
            } if dispute.resolved_by_admin else None,
            "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
            "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error fetching withdrawal dispute {dispute_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch withdrawal dispute"
        )


@router.post("/disputes/{dispute_id}/retry", response_model=Dict[str, Any])
async def retry_withdrawal_transfer(
    dispute_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retry a failed withdrawal transfer.
    Admin only endpoint.
    
    This will:
    1. Verify dispute is in OPEN status
    2. Initiate a new Paystack transfer for the withdrawal amount
    3. Update dispute resolution_action to "retry"
    4. Update dispute status to UNDER_REVIEW
    5. Send notification to user
    """
    from sqlalchemy.future import select
    from datetime import datetime
    
    try:
        result = await db.execute(
            select(Dispute).where(
                (Dispute.id == dispute_id) & 
                (Dispute.dispute_type == "withdrawal")
            )
        )
        dispute = result.scalar()
        
        if not dispute:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal dispute not found"
            )
        
        if dispute.status != DisputeStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot retry dispute in {dispute.status.value} status"
            )
        
        withdrawal_req = dispute.withdrawal_request
        
        # Initiate Paystack transfer again
        withdrawal_service = WithdrawalService(db)
        try:
            transfer_data = await withdrawal_service._initiate_paystack_transfer(
                withdrawal_request=withdrawal_req
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate transfer: {str(e)}"
            )
        
        # Update dispute
        dispute.resolution_action = "retry"
        dispute.status = DisputeStatus.UNDER_REVIEW
        
        await db.commit()
        
        payment_logger.info(
            f"Withdrawal dispute {dispute_id} retry initiated by admin {current_user.id}"
        )
        
        return {
            "dispute_id": dispute.id,
            "status": dispute.status.value,
            "resolution_action": dispute.resolution_action,
            "message": "Transfer retry initiated. User will be notified of the new transfer status.",
            "transfer_code": transfer_data.get('transfer_code')
        }
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error retrying withdrawal transfer for dispute {dispute_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry withdrawal transfer"
        )


@router.post("/disputes/{dispute_id}/refund", response_model=Dict[str, Any])
async def refund_withdrawal_to_wallet(
    dispute_id: int,
    reason: str = Query(...),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Refund a permanently failed withdrawal back to user's wallet.
    Admin only endpoint.
    
    This will:
    1. Verify dispute is in OPEN or UNDER_REVIEW status
    2. Restore withdrawal total_amount to user's wallet
    3. Update withdrawal request status to REFUNDED
    4. Update dispute resolution_action to "refund"
    5. Mark dispute as RESOLVED
    6. Send notification to user
    """
    from sqlalchemy.future import select
    from datetime import datetime
    
    if not reason or len(reason.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund reason is required"
        )
    
    try:
        result = await db.execute(
            select(Dispute).where(
                (Dispute.id == dispute_id) & 
                (Dispute.dispute_type == "withdrawal")
            )
        )
        dispute = result.scalar()
        
        if not dispute:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Withdrawal dispute not found"
            )
        
        if dispute.status == DisputeStatus.RESOLVED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot refund an already resolved dispute"
            )
        
        withdrawal_req = dispute.withdrawal_request
        user = withdrawal_req.user
        
        # Restore funds to wallet
        user.wallet_balance += withdrawal_req.total_amount
        
        # Update dispute
        dispute.resolution_action = "refund"
        dispute.status = DisputeStatus.RESOLVED
        dispute.resolution = reason
        dispute.resolved_by_admin_id = current_user.id
        dispute.resolved_at = datetime.utcnow()
        
        # Update withdrawal status
        from app.models.enums import WithdrawalRequestStatus
        withdrawal_req.status = WithdrawalRequestStatus.REFUNDED
        
        await db.commit()
        
        payment_logger.info(
            f"Withdrawal {withdrawal_req.id} refunded by admin {current_user.id}: {reason}"
        )
        
        # Send notification to user
        from app.schemas.notification import NotificationCreate
        from app.models.notification import NotificationCategory
        from app.services.notification_service import NotificationService
        
        notification_service = NotificationService(db)
        await notification_service.create_notification(NotificationCreate(
            user_id=user.id,
            title="Withdrawal Refunded",
            message=f"Your failed withdrawal of {withdrawal_req.amount} NGN has been refunded to your wallet.",
            category=NotificationCategory.PAYMENTS_AND_WALLET,
            action_screen="WithdrawalRequests",
            action_payload={"withdrawal_request_id": withdrawal_req.id}
        ))
        
        return {
            "dispute_id": dispute.id,
            "withdrawal_request_id": withdrawal_req.id,
            "status": dispute.status.value,
            "resolution_action": dispute.resolution_action,
            "refund_amount": float(withdrawal_req.total_amount),
            "user_wallet_balance": float(user.wallet_balance),
            "message": "Funds have been refunded to user's wallet. User has been notified."
        }
    except HTTPException:
        raise
    except Exception as e:
        payment_logger.error(f"Error refunding withdrawal dispute {dispute_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process withdrawal refund"
        )
