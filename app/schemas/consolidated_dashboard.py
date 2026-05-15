"""
Consolidated Dashboard Schemas

Single response containing all data needed for employer and worker home screens.
This eliminates the need for multiple parallel API calls on the mobile client.
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from app.schemas.user import UserOut as UserSchema
from app.schemas.job import JobInDB as JobSchema
from app.schemas.employer_dashboard import (
    DashboardMetricsSchema,
    EnrichedRecentActivitySchema,
    ActiveJobSchema,
    WorkerListItemSchema,
    ServiceListItemSchema,
    ActivityType
)
from app.schemas.worker_dashboard import (
    WorkerStats,
    ApplicationWithAction,
    BoostActivitySchema
)
from app.schemas.job_application import JobApplicationInDB as JobApplicationSchema
from app.schemas.recent_activity import RecentActivityOut as RecentActivitySchema


class DashboardMetadata(BaseModel):
    """Metadata about the dashboard response"""
    created_at: datetime
    version: str = "1.0"  # API version for compatibility

    class Config:
        from_attributes = True


class PendingApplicationSchema(BaseModel):
    """Pending application for dashboard"""
    id: int
    job_id: int
    worker_id: int
    worker_name: str
    worker_avatar: Optional[str] = None
    worker_rating: float = 0.0
    proposal: Optional[str] = None
    status: str
    applied_at: datetime

    class Config:
        from_attributes = True


class DensityPointSchema(BaseModel):
    """Lightweight point for home density map rendering."""
    id: str
    category_id: str
    latitude: float
    longitude: float

    class Config:
        from_attributes = True


# ============================================================================
# EMPLOYER CONSOLIDATED DASHBOARD
# ============================================================================

class EmployerConsolidatedDashboardSchema(BaseModel):
    """
    Complete employer home screen data in a single response.
    
    This consolidates all data previously fetched via multiple API calls:
    - /employer/dashboard → Main metrics and activities
    - /employer/metrics → Stats
    - /employer/activities → Recent activities
    - /employer/jobs/active → Active jobs
    - /employer/applications/pending → Pending applications
    - /workers/top → Top workers
    - /workers/nearby/list → Nearby workers
    - /services/nearby/list → Nearby services
    - Notifications count → Unread notifications
    - Messages count → Unread messages
    """
    metadata: DashboardMetadata
    user: UserSchema
    
    # Core metrics
    stats: DashboardMetricsSchema
    
    # Recent activities (limited, top 10)
    recent_activities: List[EnrichedRecentActivitySchema]
    
    # Active/posted jobs (limited, top 5)
    active_jobs: List[ActiveJobSchema]
    
    # Pending applications from workers (limited, top 5)
    pending_applications: List[PendingApplicationSchema]
    
    # Discovery: nearby and top workers for recommendations
    nearby_workers: List[WorkerListItemSchema]  # 10 max
    top_workers: List[WorkerListItemSchema]  # 10 max
    
    # Discovery: nearby and featured services
    nearby_services: List[ServiceListItemSchema]  # 10 max
    category_counts: Dict[str, int] = {}
    density_points: List[DensityPointSchema] = []
    
    # Notification counts
    unread_notifications_count: int
    unread_messages_count: int

    class Config:
        from_attributes = True


# ============================================================================
# WORKER CONSOLIDATED DASHBOARD
# ============================================================================

class WorkerConsolidatedDashboardSchema(BaseModel):
    """
    Complete worker home screen data in a single response.
    
    This consolidates all data previously fetched via multiple API calls:
    - /worker/dashboard → Main dashboard data
    - /worker/dashboard/active-contracts → Active jobs
    - /worker/metrics → Stats
    - /jobs/worker/available → Recommended jobs
    - /worker/dashboard/applications-with-actions → Applications with actions
    - Notifications → Unread notifications and messages
    """
    metadata: DashboardMetadata
    user: UserSchema
    
    # Core statistics
    stats: WorkerStats
    
    # Recommended available jobs (limited, top 5)
    recommended_jobs: List[JobSchema]
    
    # User's job applications (limited, top 10)
    applications: List[JobApplicationSchema]
    
    # Recent activity (limited, top 10)
    recent_activity: List[RecentActivitySchema]
    
    # Applications with recommended actions (limited, top 3)
    applications_with_actions: List[ApplicationWithAction]
    
    # Recent boost activities (limited, top 5)
    boost_activities: List[BoostActivitySchema]

    # Lightweight discovery metadata for category chips/map overlays
    category_counts: Dict[str, int] = {}
    density_points: List[DensityPointSchema] = []
    
    # Notification and message counts
    unread_notifications_count: int
    unread_messages_count: int

    class Config:
        from_attributes = True


# ============================================================================
# OPTIONAL: Query parameter schemas for flexible dashboard requests
# ============================================================================

class DashboardQueryParams(BaseModel):
    """Optional query parameters to customize dashboard response"""
    # Comma-separated list of sections to include (e.g., "stats,jobs,notifications")
    # If omitted, returns everything
    include_sections: Optional[str] = None
    
    # Override default limits
    limit_activities: Optional[int] = None  # Default: 10
    limit_jobs: Optional[int] = None  # Default: 5
    limit_applications: Optional[int] = None  # Default: 10
    limit_workers: Optional[int] = None  # Default: 10
    limit_services: Optional[int] = None  # Default: 10

    class Config:
        from_attributes = True
