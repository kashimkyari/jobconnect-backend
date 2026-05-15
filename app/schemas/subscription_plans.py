from typing import Dict, List


# Subscription Plans Configuration
SUBSCRIPTION_PLANS = {
    # WORKER/FREELANCER PLANS
    "worker_basic": {
        "id": 1,
        "label": "Freelancer Basic",
        "user_type": "worker",
        "price_monthly": 2999,
        "price_annually": 29990,  # 15% discount (approx ₦29,990 vs ₦35,988)
        "currency": "NGN",
        "features": {
            "commission_reduction": 0.005,  # From 1.5% to 1.0%
            "priority_support": False,
            "tax_documents": True,
            "featured_profile": False,
            "analytics": False,
            "api_access": False,
            "applications_per_month": None,  # Unlimited
        },
        "description": "Perfect for freelancers starting out"
    },
    
    "worker_pro": {
        "id": 2,
        "label": "Freelancer Pro",
        "user_type": "worker",
        "price_monthly": 9999,
        "price_annually": 99990,  # 15% discount
        "currency": "NGN",
        "features": {
            "commission_reduction": 0.008,  # From 1.5% to 0.7%
            "priority_support": True,
            "tax_documents": True,
            "featured_profile": True,
            "analytics": True,
            "api_access": False,
            "applications_per_month": None,  # Unlimited
            "featured_profile_boosts_monthly": 2,
        },
        "description": "For established freelancers wanting more visibility"
    },
    
    "worker_enterprise": {
        "id": 3,
        "label": "Freelancer Enterprise",
        "user_type": "worker",
        "price_monthly": 29999,
        "price_annually": 299990,  # 15% discount
        "currency": "NGN",
        "features": {
            "commission_reduction": 0.010,  # From 1.5% to 0.5%
            "priority_support": True,
            "tax_documents": True,
            "featured_profile": True,
            "analytics": True,
            "api_access": True,
            "applications_per_month": None,  # Unlimited
            "featured_profile_boosts_monthly": 5,
            "dedicated_account_manager": True,
        },
        "description": "For top-performing freelancers and agencies"
    },
    
    # EMPLOYER/CLIENT PLANS
    "employer_starter": {
        "id": 4,
        "label": "Employer Starter",
        "user_type": "employer",
        "price_monthly": 4999,
        "price_annually": 49990,  # 15% discount
        "currency": "NGN",
        "features": {
            "job_posts_per_month": 10,
            "featured_job_slots": 0,
            "priority_support": False,
            "recruiter_tools": False,
            "candidate_analytics": False,
            "api_access": False,
            "team_members": 1,
        },
        "description": "For small businesses posting occasional jobs"
    },
    
    "employer_professional": {
        "id": 5,
        "label": "Employer Professional",
        "user_type": "employer",
        "price_monthly": 14999,
        "price_annually": 149990,  # 15% discount
        "currency": "NGN",
        "features": {
            "job_posts_per_month": 50,
            "featured_job_slots": 2,
            "priority_support": True,
            "recruiter_tools": True,
            "candidate_analytics": True,
            "api_access": False,
            "team_members": 3,
            "job_recommendations": True,
        },
        "description": "For growing companies with regular hiring"
    },
    
    "employer_enterprise": {
        "id": 6,
        "label": "Employer Enterprise",
        "user_type": "employer",
        "price_monthly": 39999,
        "price_annually": 399990,  # 15% discount
        "currency": "NGN",
        "features": {
            "job_posts_per_month": None,  # Unlimited
            "featured_job_slots": 10,
            "priority_support": True,
            "recruiter_tools": True,
            "candidate_analytics": True,
            "api_access": True,
            "team_members": None,  # Unlimited
            "job_recommendations": True,
            "dedicated_account_manager": True,
            "custom_branding": True,
        },
        "description": "For enterprise organizations with high-volume hiring"
    },
}


def get_plan_by_id(plan_id: int) -> Dict:
    """Get plan details by ID"""
    for plan_key, plan_data in SUBSCRIPTION_PLANS.items():
        if plan_data["id"] == plan_id:
            return plan_data
    return None


def get_plans_by_user_type(user_type: str) -> List[Dict]:
    """Get all plans for a specific user type"""
    return [
        plan for plan in SUBSCRIPTION_PLANS.values()
        if plan["user_type"] == user_type
    ]
