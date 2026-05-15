from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, desc
from fastapi import HTTPException, status
from typing import List, Optional

from ..models.subscription import SubscriptionPlan
from ..schemas.subscription_admin_schemas import SubscriptionPlanCreate, SubscriptionPlanUpdate
from ..utils.logging import app_logger


class SubscriptionAdminService:
    """Service for admin subscription plan management"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_plan(self, plan_data: SubscriptionPlanCreate, admin_id: int) -> SubscriptionPlan:
        """Create a new subscription plan"""
        # Check if plan with this name already exists
        query = select(SubscriptionPlan).where(SubscriptionPlan.name == plan_data.name)
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subscription plan with name '{plan_data.name}' already exists"
            )
        
        # Create new plan
        plan = SubscriptionPlan(
            name=plan_data.name,
            label=plan_data.label,
            user_type=plan_data.user_type,
            description=plan_data.description,
            price_monthly=plan_data.price_monthly,
            price_annually=plan_data.price_annually,
            currency=plan_data.currency,
            features=plan_data.features,
            is_active=plan_data.is_active,
            is_recommended=plan_data.is_recommended,
            sort_order=plan_data.sort_order,
            created_by_admin_id=admin_id,
        )
        
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        
        app_logger.info(
            f"Subscription plan created: {plan.name}",
            extra={"admin_id": admin_id, "plan_id": plan.id}
        )
        
        return plan
    
    async def update_plan(self, plan_id: int, plan_data: SubscriptionPlanUpdate, admin_id: int) -> SubscriptionPlan:
        """Update a subscription plan"""
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        
        # Check if new name conflicts with existing plan
        if plan_data.name and plan_data.name != plan.name:
            query = select(SubscriptionPlan).where(SubscriptionPlan.name == plan_data.name)
            result = await self.db.execute(query)
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Subscription plan with name '{plan_data.name}' already exists"
                )
        
        # Update fields if provided
        update_data = plan_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(plan, field, value)
        
        await self.db.commit()
        await self.db.refresh(plan)
        
        app_logger.info(
            f"Subscription plan updated: {plan.name}",
            extra={"admin_id": admin_id, "plan_id": plan.id}
        )
        
        return plan
    
    async def delete_plan(self, plan_id: int, admin_id: int) -> dict:
        """Delete a subscription plan"""
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        
        plan_name = plan.name
        await self.db.delete(plan)
        await self.db.commit()
        
        app_logger.info(
            f"Subscription plan deleted: {plan_name}",
            extra={"admin_id": admin_id, "plan_id": plan_id}
        )
        
        return {"status": "success", "message": f"Plan '{plan_name}' deleted"}
    
    async def get_plan(self, plan_id: int) -> SubscriptionPlan:
        """Get a single subscription plan by ID"""
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        return plan
    
    async def get_plans_by_user_type(self, user_type: str, active_only: bool = True) -> List[SubscriptionPlan]:
        """Get subscription plans filtered by user type"""
        query = select(SubscriptionPlan).where(SubscriptionPlan.user_type == user_type)
        
        if active_only:
            query = query.where(SubscriptionPlan.is_active == True)
        
        query = query.order_by(SubscriptionPlan.sort_order, SubscriptionPlan.created_at)
        result = await self.db.execute(query)
        
        return result.scalars().all()
    
    async def get_all_plans(self, user_type: Optional[str] = None, active_only: bool = False) -> List[SubscriptionPlan]:
        """Get all subscription plans with optional filters"""
        query = select(SubscriptionPlan)
        
        if user_type:
            query = query.where(SubscriptionPlan.user_type == user_type)
        
        if active_only:
            query = query.where(SubscriptionPlan.is_active == True)
        
        query = query.order_by(SubscriptionPlan.sort_order, SubscriptionPlan.is_recommended.desc(), SubscriptionPlan.created_at)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def toggle_plan_status(self, plan_id: int, admin_id: int) -> SubscriptionPlan:
        """Enable or disable a subscription plan"""
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        
        plan.is_active = not plan.is_active
        await self.db.commit()
        await self.db.refresh(plan)
        
        app_logger.info(
            f"Subscription plan toggled: {plan.name} -> {plan.is_active}",
            extra={"admin_id": admin_id, "plan_id": plan.id}
        )
        
        return plan
    
    async def set_recommended(self, plan_id: int, is_recommended: bool, admin_id: int) -> SubscriptionPlan:
        """Mark plan as recommended or not"""
        plan = await self.db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription plan not found"
            )
        
        plan.is_recommended = is_recommended
        await self.db.commit()
        await self.db.refresh(plan)
        
        app_logger.info(
            f"Subscription plan recommendation updated: {plan.name}",
            extra={"admin_id": admin_id, "plan_id": plan.id, "is_recommended": is_recommended}
        )
        
        return plan
