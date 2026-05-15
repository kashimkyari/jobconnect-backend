from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from .database import async_session, engine
from .config import settings
from .sentry import init_sentry
from .utils.logging import app_logger
from .routers import (
    auth,
    users,
    jobs,
    messages,
    reviews,
    payments,
    badges,
    kyc,
    admin,
    files,
    notification,
    dashboard,
    dispute,
    subscription,
    worker,
    workers,
    recent_activity,
    waitlist,
    referral,
    categories,
    employer_dashboard,
    profile_views,
    security,
    transactions,
    block,
    notification_settings,
    applicants,
    worker_dashboard,
    meta,
    calls,
    withdrawal,
    withdrawal_admin,
    bank_accounts,
    banks,
    contracts,
    services,
    tax_compliance,
    subscription_admin,
    discovery,
    bookings,
    stories,
    consolidated_dashboard,
    revenuecat,
    session,
    search
)
from .middlewares.rate_limiter import RateLimitMiddleware
from .middlewares.error_handler import ErrorHandlerMiddleware
from .middlewares.db_session_middleware import DBSessionMiddleware
from .middlewares.activity_middleware import ActivityMiddleware
from .scheduler import init_scheduler

init_sentry(settings)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middlewares
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(DBSessionMiddleware)
app.add_middleware(ActivityMiddleware)


@app.on_event("shutdown")
async def shutdown_event():
    app_logger.info("Closing database connection pool...")
    await engine.dispose()


# Add Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Mount static files directory
app.mount("/uploads", StaticFiles(directory="storage/uploads"), name="uploads")

# Initialize scheduler
@app.on_event("startup")
async def startup_event():
    init_scheduler()

# Include routers
app.include_router(auth.router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["Users"])
app.include_router(jobs.router, prefix=f"{settings.API_V1_PREFIX}/jobs", tags=["Jobs"])
app.include_router(messages.router, prefix=f"{settings.API_V1_PREFIX}/messages", tags=["Messages"])
app.include_router(reviews.router, prefix=f"{settings.API_V1_PREFIX}/reviews", tags=["Reviews"])
app.include_router(payments.router, prefix=f"{settings.API_V1_PREFIX}/payments", tags=["Payments"])
app.include_router(badges.router, prefix=f"{settings.API_V1_PREFIX}/badges", tags=["Badges"])
app.include_router(kyc.router, prefix=f"{settings.API_V1_PREFIX}/kyc", tags=["KYC"])
app.include_router(admin.router, prefix=f"{settings.API_V1_PREFIX}/admin", tags=["Admin"])
app.include_router(files.router, prefix=f"{settings.API_V1_PREFIX}/files", tags=["Files"])
app.include_router(notification.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Notifications"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_PREFIX}/dashboard", tags=["Dashboard"])
app.include_router(dispute.router, prefix=f"{settings.API_V1_PREFIX}/disputes", tags=["Disputes"])
app.include_router(subscription.router, prefix=f"{settings.API_V1_PREFIX}/subscriptions", tags=["Subscriptions"])
app.include_router(worker.router, prefix=f"{settings.API_V1_PREFIX}/worker", tags=["Worker"])
app.include_router(workers.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Workers"])
app.include_router(recent_activity.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Recent Activity"])
app.include_router(waitlist.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Waitlist"])
app.include_router(referral.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Referrals"])
app.include_router(categories.router, prefix=f"{settings.API_V1_PREFIX}/categories", tags=["Categories"])
app.include_router(employer_dashboard.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Employer Dashboard"])
app.include_router(consolidated_dashboard.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Consolidated Dashboard"])
app.include_router(profile_views.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Profile Views"])
app.include_router(security.router, prefix=f"{settings.API_V1_PREFIX}/security", tags=["Security"])
app.include_router(transactions.router, prefix=f"{settings.API_V1_PREFIX}/transactions", tags=["Transactions"])
app.include_router(block.router, prefix=f"{settings.API_V1_PREFIX}/block", tags=["Block"])
app.include_router(notification_settings.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Notification Settings"])
app.include_router(applicants.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Applicants"])
app.include_router(worker_dashboard.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Worker Dashboard"])
app.include_router(contracts.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Contracts"])
app.include_router(meta.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Meta"])
app.include_router(calls.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Calls"])
app.include_router(withdrawal.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Withdrawal"])
app.include_router(withdrawal_admin.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Admin - Withdrawals"])
app.include_router(bank_accounts.router, prefix=f"{settings.API_V1_PREFIX}/users/me/banks", tags=["Bank Accounts"])
app.include_router(banks.router, prefix=f"{settings.API_V1_PREFIX}/payments", tags=["Banks"])
app.include_router(services.router, prefix=f"{settings.API_V1_PREFIX}/services", tags=["Services"])
app.include_router(tax_compliance.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Tax"])
app.include_router(subscription_admin.router, prefix=f"{settings.API_V1_PREFIX}/admin/subscriptions", tags=["Admin - Subscriptions"])
app.include_router(discovery.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Discovery"])
app.include_router(bookings.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Bookings"])
app.include_router(stories.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Stories"])
app.include_router(revenuecat.router, prefix=f"{settings.API_V1_PREFIX}/revenuecat", tags=["RevenueCat"])
app.include_router(session.router, prefix=f"{settings.API_V1_PREFIX}/sessions", tags=["Sessions"])
app.include_router(search.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Search"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
