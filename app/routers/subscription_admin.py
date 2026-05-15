from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from ..database import get_db
from ..services.auth_service import get_admin_user
from ..services.subscription_admin_service import SubscriptionAdminService
from ..schemas.subscription_admin_schemas import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
    SubscriptionPlanResponse,
    SubscriptionPlanListResponse,
    SubscriptionPlanDetailResponse,
)
from ..utils.logging import app_logger

router = APIRouter(tags=["Admin - Subscriptions"])


@router.post("/plans", response_model=SubscriptionPlanDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription_plan(
    plan_data: SubscriptionPlanCreate,
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new subscription plan (Admin only)
    
    Requires admin role. Creates a new subscription plan with the provided details.
    """
    try:
        service = SubscriptionAdminService(db)
        plan = await service.create_plan(plan_data, admin_user.id)
        
        return {
            "status": "success",
            "data": plan
        }
    except Exception as e:
        app_logger.error(f"Error creating subscription plan: {str(e)}", extra={"admin_id": admin_user.id})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans", response_model=SubscriptionPlanListResponse)
async def list_subscription_plans(
    user_type: Optional[str] = Query(None, description="Filter by 'worker' or 'employer'"),
    active_only: bool = Query(False, description="Show only active plans"),
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all subscription plans (Admin only)
    
    Optional filters:
    - user_type: Filter by 'worker' or 'employer'
    - active_only: Show only active plans (true/false)
    """
    try:
        service = SubscriptionAdminService(db)
        plans = await service.get_all_plans(user_type=user_type, active_only=active_only)
        
        return {
            "status": "success",
            "data": plans,
            "count": len(plans)
        }
    except Exception as e:
        app_logger.error(f"Error listing subscription plans: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans/{plan_id}", response_model=SubscriptionPlanDetailResponse)
async def get_subscription_plan(
    plan_id: int,
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific subscription plan by ID (Admin only)
    """
    try:
        service = SubscriptionAdminService(db)
        plan = await service.get_plan(plan_id)
        
        return {
            "status": "success",
            "data": plan
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error fetching subscription plan: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/plans/{plan_id}", response_model=SubscriptionPlanDetailResponse)
async def update_subscription_plan(
    plan_id: int,
    plan_data: SubscriptionPlanUpdate,
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a subscription plan (Admin only)
    
    All fields are optional. Only provided fields will be updated.
    """
    try:
        service = SubscriptionAdminService(db)
        plan = await service.update_plan(plan_id, plan_data, admin_user.id)
        
        return {
            "status": "success",
            "data": plan
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error updating subscription plan: {str(e)}", extra={"admin_id": admin_user.id})
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/plans/{plan_id}", response_model=dict)
async def delete_subscription_plan(
    plan_id: int,
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a subscription plan (Admin only)
    
    WARNING: This will delete the plan from the system.
    """
    try:
        service = SubscriptionAdminService(db)
        result = await service.delete_plan(plan_id, admin_user.id)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error deleting subscription plan: {str(e)}", extra={"admin_id": admin_user.id})
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/plans/{plan_id}/toggle-status")
async def toggle_plan_status(
    plan_id: int,
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle subscription plan active/inactive status (Admin only)
    """
    try:
        service = SubscriptionAdminService(db)
        plan = await service.toggle_plan_status(plan_id, admin_user.id)
        
        return {
            "status": "success",
            "message": f"Plan '{plan.name}' is now {'active' if plan.is_active else 'inactive'}",
            "data": plan
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error toggling plan status: {str(e)}", extra={"admin_id": admin_user.id})
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/plans/{plan_id}/set-recommended")
async def set_plan_recommended(
    plan_id: int,
    is_recommended: bool = Query(..., description="True to mark as recommended, False to unmark"),
    admin_user = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Set or unset a plan as recommended (Admin only)
    """
    try:
        service = SubscriptionAdminService(db)
        plan = await service.set_recommended(plan_id, is_recommended, admin_user.id)
        
        return {
            "status": "success",
            "message": f"Plan '{plan.name}' is now {'recommended' if plan.is_recommended else 'not recommended'}",
            "data": plan
        }
    except HTTPException:
        raise
    except Exception as e:
        app_logger.error(f"Error setting plan recommendation: {str(e)}", extra={"admin_id": admin_user.id})
        raise HTTPException(status_code=500, detail=str(e))


# Public endpoint to get subscription plans (used by mobile app)
@router.get("/public/plans", include_in_schema=True, tags=["Public"])
async def get_public_subscription_plans(
    user_type: Optional[str] = Query(None, description="'worker' or 'employer'"),
    db: AsyncSession = Depends(get_db)
):
    """
    Public endpoint to get active subscription plans for users
    
    Returns only active plans suitable for the specified user type.
    """
    try:
        service = SubscriptionAdminService(db)
        plans = await service.get_plans_by_user_type(user_type) if user_type else await service.get_all_plans(active_only=True)
        
        return {
            "status": "success",
            "data": plans,
            "count": len(plans)
        }
    except Exception as e:
        app_logger.error(f"Error fetching public subscription plans: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
