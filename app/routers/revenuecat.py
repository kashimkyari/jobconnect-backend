import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from app.models.subscription import SubscriptionPlan
from app.services.notification_service import NotificationService
from app.models.notification import NotificationCategory
from app.schemas.notification import NotificationCreate
from app.utils.logging import StructuredLogger

logger = StructuredLogger("revenuecat_webhook")

router = APIRouter()

# Set in your production environment
REVENUECAT_WEBHOOK_AUTH_TOKEN = os.getenv("REVENUECAT_WEBHOOK_AUTH_TOKEN", "")

@router.post("/webhook")
async def revenuecat_webhook(
    request: Request,
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    # Verify Authorization if token is set
    if REVENUECAT_WEBHOOK_AUTH_TOKEN:
        # Accept both "Bearer <token>" and just "<token>" for flexibility
        is_bearer = authorization and authorization.startswith("Bearer ")
        token_to_check = authorization.replace("Bearer ", "") if is_bearer else authorization
        
        if token_to_check != REVENUECAT_WEBHOOK_AUTH_TOKEN:
            logger.warning(f"Unauthorized access attempt to RevenueCat webhook. Header present: {bool(authorization)}")
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse RevenueCat webhook payload: {str(e)}")
        return {"status": "error", "message": "Invalid JSON"}

    event = payload.get("event", {})
    event_type = event.get("type")
    
    # RevenueCat passes the ID we used in Purchases.logIn(appUserID)
    app_user_id_str = event.get("app_user_id")
    
    if not app_user_id_str:
        logger.warning(f"Ignored RevenueCat event: missing app_user_id")
        return {"status": "ignored", "reason": "Missing app_user_id"}

    if not str(app_user_id_str).isdigit():
        logger.warning(f"Ignored RevenueCat event: app_user_id '{app_user_id_str}' is not an integer ID. Ensure Purchases.logIn() uses the database numeric ID.")
        return {"status": "ignored", "reason": "Invalid app_user_id format (expected numeric ID)"}
        
    user_id = int(app_user_id_str)
    user = await db.get(User, user_id)
    if not user:
        logger.warning(f"Ignored RevenueCat event: User ID {user_id} not found in database.")
        return {"status": "ignored", "reason": "User not found"}
        
    notification_service = NotificationService(db)

    logger.info(f"Processing RevenueCat event: {event_type} for User: {user_id}")

    if event_type in ["INITIAL_PURCHASE", "RENEWAL"]:
        product_id = event.get("product_id", "")
        expiration_ms = event.get("expiration_at_ms")
        
        # Determine plan from product_id
        plan = None
        result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active == True))
        all_plans = result.scalars().all()
        for p in all_plans:
            if not p.name: 
                continue
            if p.name.lower() in product_id.lower() or product_id.lower() in p.name.lower():
                plan = p
                break
        
        # Fallback to role-based plan if not matched by name
        if not plan and all_plans:
            for p in all_plans:
                if p.user_type == user.role.value:
                    plan = p
                    break
        
        user.subscription_status = True
        if expiration_ms:
            user.subscription_expiry = datetime.fromtimestamp(expiration_ms / 1000.0, tz=timezone.utc)
            
        if plan:
            user.subscription_plan_id = plan.id
            features = plan.features or {}
            user.remaining_job_posts = features.get("job_posts", 0)
            user.remaining_job_applications = features.get("job_applications", 0)
            
        await db.commit()
        
        title = "Subscription Activated" if event_type == "INITIAL_PURCHASE" else "Subscription Renewed"
        msg = "Your premium subscription has been activated successfully." if event_type == "INITIAL_PURCHASE" else "Your premium subscription has been renewed."
        
        await notification_service.create_notification(
            NotificationCreate(
                user_id=user.id, title=title, message=msg, category=NotificationCategory.PAYMENTS_AND_WALLET
            )
        )
        
    elif event_type in ["CANCELLATION", "EXPIRATION", "BILLING_ISSUE"]:
        user.subscription_status = False
        user.subscription_plan_id = None
        user.subscription_expiry = None
        user.remaining_job_posts = 0
        user.remaining_job_applications = 0
        await db.commit()
        
        await notification_service.create_notification(
            NotificationCreate(
                user_id=user.id, title="Subscription Ended", message="Your premium subscription has ended or was canceled.", category=NotificationCategory.PAYMENTS_AND_WALLET
            )
        )

    return {"status": "success"}
