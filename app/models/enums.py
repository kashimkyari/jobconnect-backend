import enum

class UserRole(str, enum.Enum):
    EMPLOYER = "employer"
    WORKER = "worker"
    ADMIN = "admin"

class PricingModel(str, enum.Enum):
    FIXED_PRICE = "fixed_price"
    HOURLY = "hourly"

class TaxPreference(str, enum.Enum):
    """Tax calculation preference for withdrawals"""
    BEFORE = "before"  # Add tax on top of amount (user pays extra)
    AFTER = "after"    # Deduct tax from amount (user gets less)

class WithdrawalRequestStatus(str, enum.Enum):
    """Status of withdrawal requests"""
    PENDING = "pending"          # Awaiting admin approval
    APPROVED = "approved"        # Admin approved, Paystack transfer initiated
    DECLINED = "declined"        # Admin declined, funds restored
    PROCESSING = "processing"    # Transfer in progress
    COMPLETED = "completed"      # Transfer completed successfully
    FAILED = "failed"           # Transfer failed
    REFUNDED = "refunded"       # Failed transfer refunded to wallet

class BookingStatus(str, enum.Enum):
    """Status of service bookings"""
    BOOKED = "booked"           # Request sent
    CONFIRMED = "confirmed"     # Worker accepted the booking
    EN_ROUTE = "en_route"       # Worker on the way
    ARRIVED = "arrived"         # Worker arrived on-site
    IN_PROGRESS = "in_progress" # Job underway
    DONE = "done"               # Worker marked job done
    PENDING = "pending"         # Backward-compat: awaiting worker response
    ACCEPTED = "accepted"       # Backward-compat: worker accepted
    REJECTED = "rejected"       # Worker rejected the booking
    CANCELLED = "cancelled"     # Employer cancelled the booking
    COMPLETED = "completed"     # Service completed (escrow released)
