from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.schemas import subscription as subscription_schema, user as user_schema
from app.database import get_db as get_async_db
from app.services.subscription_service import SubscriptionService
from app.utils.security import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/subscription-plans/", response_model=subscription_schema.SubscriptionPlanInDB)
async def create_subscription_plan(
    plan: subscription_schema.SubscriptionPlanCreate, db: AsyncSession = Depends(get_async_db)
):
    service = SubscriptionService(db)
    return await service.create_subscription_plan(plan)

@router.get("/subscription-plans/", response_model=List[subscription_schema.SubscriptionPlanInDB])
async def read_subscription_plans(db: AsyncSession = Depends(get_async_db)):
    service = SubscriptionService(db)
    return await service.get_subscription_plans()

@router.post("/subscribe/", response_model=subscription_schema.SubscriptionPlanInDB)
async def subscribe_user(
    subscription: subscription_schema.SubscriptionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    service = SubscriptionService(db)
    result = await service.subscribe_user(
        user_id=current_user.id,
        plan_id=subscription.plan_id,
        billing_cycle=subscription.billing_cycle,
    )
    return result

@router.get("/my-subscription/", response_model=Optional[subscription_schema.UserSubscriptionResponse])
async def get_my_subscription(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    service = SubscriptionService(db)
    subscription = await service.get_user_subscription(user_id=current_user.id)
    if not subscription:
        return None
    return subscription

@router.post("/cancel/")
async def cancel_subscription(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    service = SubscriptionService(db)
    result = await service.cancel_subscription(user_id=current_user.id)
    return result
