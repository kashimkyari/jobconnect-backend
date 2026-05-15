# JobConnect Backend

A comprehensive FastAPI-based backend for the JobConnect peer-to-peer marketplace platform, enabling employers to post jobs and workers to apply, collaborate, and earn through a secure payment system with built-in escrow management.

## 🎯 Core Features

### User Management & Authentication
- **JWT-based authentication** with refresh token mechanism
- **Role-based access control** (Employer, Worker, Admin)
- **Account security** with login attempt tracking and lockout protection
- **Multi-channel verification** (Email OTP, SMS verification via Twilio)
- **KYC (Know Your Customer)** verification system with document uploads
- **User profiles** with reputation scoring and wallet management

### Job Marketplace
- **Job posting & management** with category-based organization
- **Job applications** with proposed budgets and cover letters
- **Application status tracking** (Pending, Accepted, Rejected, Withdrawn)
- **Location-based filtering** (Remote, On-site, Hybrid)
- **High-value job management** with special handling
- **Job search & discovery** with advanced filtering

### Payment & Financial Management
- **Paystack integration** for secure payment processing
- **Escrow system** for safe fund holding during job execution
- **Multiple payment types** (Escrow, Application Fee, Wallet Funding, Subscription, Withdrawals)
- **Wallet system** for users to hold and manage funds
- **Commission management** with configurable rates
- **Transaction history** and financial reporting
- **Subscription plans** (Basic, Pro) with tiered features

### Disputes & Quality Assurance
- **Dispute resolution system** for job-related conflicts
- **Dispute status tracking** (Open, Under Review, Resolved)
- **Admin arbitration tools** for dispute management
- **Claim and defense mechanisms** for fair resolution

### Reviews & Reputation
- **Rating system** (1-5 stars) for jobs and users
- **Review & feedback** mechanism for post-job evaluation
- **Reputation scoring** based on reviews and activity
- **Worker badges** (achievements) system
- **Review filtering & moderation**

### Communication & Notifications
- **In-app messaging** with real-time updates via WebSocket
- **Content filtering** for message safety
- **Email notifications** via SMTP (Mailgun-compatible)
- **SMS notifications** via Twilio
- **Push notifications** support
- **Notification preferences** management

### Admin & Analytics
- **Admin dashboard** with comprehensive analytics
- **User management & moderation**
- **Job & application monitoring**
- **Payment & transaction tracking**
- **Dispute management interface**
- **System analytics & reporting**
- **Revenue management** and commission tracking

### Additional Features
- **Referral system** with reward incentives
- **Newsletter management** with email campaigns
- **File upload management** (avatars, job attachments, KYC documents)
- **Database replication** (Write/Read separation)
- **Rate limiting** to prevent abuse
- **Prometheus metrics** for monitoring
- **Background tasks** via Celery (notifications, cleanup, payments, newsletter)
- **Comprehensive error handling** and logging

## 📊 Tech Stack

### Core Framework
- **FastAPI** - Modern, async-first Python web framework
- **Uvicorn** - ASGI server for production deployment

### Database & ORM
- **PostgreSQL** - Relational database with replication support
- **SQLAlchemy 2.0** - Async ORM with powerful query capabilities
- **Alembic** - Database migration management
- **asyncpg** - PostgreSQL async driver

### Authentication & Security
- **python-jose** - JWT token handling with cryptography
- **bcrypt** - Password hashing and verification
- **passlib** - Password utilities
- **TrustedHostMiddleware** - Host verification

### External Integrations
- **Paystack API** - Payment processing
- **Twilio** - SMS notifications
- **aiosmtplib** - Async email sending
- **aiohttp/httpx** - Async HTTP requests
- **boto3** - AWS S3 integration for file storage

### Background Processing
- **Celery** - Distributed task queue
- **Redis** - Message broker and caching
- **APScheduler** - Task scheduling

### Monitoring & Performance
- **Prometheus** - Metrics collection and monitoring
- **python-dateutil** - Date/time utilities

### Data Validation
- **Pydantic v2** - Data validation with Python type annotations
- **email-validator** - Email validation

### Development & Testing
- **pytest** - Testing framework with async support
- **pytest-asyncio** - Async test support
- **pytest-cov** - Code coverage
- **pytest-mock** - Mocking utilities
- **factory-boy** - Test data factories
- **Faker** - Synthetic data generation
- **black** - Code formatting
- **isort** - Import sorting
- **mypy** - Static type checking

## 🏗️ Project Structure

```
backend/
├── alembic/                           # Database migrations
│   ├── versions/                      # Migration scripts
│   ├── env.py                        # Migration configuration
│   └── script.py.mako                # Migration template
├── app/
│   ├── main.py                       # FastAPI application entrypoint
│   ├── config.py                     # Application settings (from .env)
│   ├── database.py                   # SQLAlchemy async session setup & DB routing
│   ├── celery_worker.py              # Celery configuration & task imports
│   ├── websocket_manager.py          # WebSocket connection management
│   │
│   ├── db/
│   │   └── base_class.py             # SQLAlchemy declarative base
│   │
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── __init__.py               # Model imports (maintains dependency order)
│   │   ├── user.py                   # User accounts with roles, wallet, reputation
│   │   ├── job.py                    # Job postings with budget & location info
│   │   ├── job_application.py        # Job applications from workers
│   │   ├── payment.py                # Payment records & transaction tracking
│   │   ├── escrow_transaction.py     # Escrow fund management
│   │   ├── review.py                 # User reviews & ratings
│   │   ├── dispute.py                # Dispute & conflict resolution
│   │   ├── message.py                # In-app messaging
│   │   ├── notification.py           # User notifications
│   │   ├── kyc.py                    # KYC submissions & verification
│   │   ├── file.py                   # File uploads (avatars, attachments, etc.)
│   │   ├── badge.py                  # Achievement badges & user badges
│   │   ├── subscription.py           # Subscription plans & user subscriptions
│   │   ├── worker_profile.py         # Worker profiles (recent work, services)
│   │   ├── category.py               # Job categories
│   │   ├── service.py                # Services & service categories
│   │   ├── otp.py                    # One-time password management
│   │   ├── token_blacklist.py        # Invalidated JWT tokens
│   │   ├── recent_activity.py        # User activity tracking
│   │   ├── referral.py               # Referral system & rewards
│   │   ├── transaction.py            # Financial transactions
│   │   ├── countdown.py              # Launch countdown feature
│   │   ├── newsletter.py             # Newsletter campaigns
│   │   ├── waitlist.py               # Pre-launch waitlist
│   │   ├── user_role.py              # User role enumerations
│   │   ├── enums.py                  # General enumerations
│   │
│   ├── schemas/                      # Pydantic validation schemas
│   │   ├── auth.py                   # Authentication request/response schemas
│   │   ├── user.py                   # User DTOs
│   │   ├── job.py                    # Job DTOs
│   │   ├── payment.py                # Payment DTOs
│   │   ├── review.py                 # Review DTOs
│   │   ├── message.py                # Message DTOs
│   │   ├── notification.py           # Notification DTOs
│   │   ├── kyc.py                    # KYC submission DTOs
│   │   ├── badge.py                  # Badge DTOs
│   │   ├── subscription.py           # Subscription DTOs
│   │   └── [others]                  # Additional schema files
│   │
│   ├── routers/                      # API endpoint definitions
│   │   ├── auth.py                   # Authentication endpoints (login, register)
│   │   ├── users.py                  # User profile endpoints
│   │   ├── jobs.py                   # Job posting & search endpoints
│   │   ├── payments.py               # Payment & transaction endpoints
│   │   ├── reviews.py                # Review endpoints
│   │   ├── messages.py               # Messaging endpoints
│   │   ├── notifications.py          # Notification endpoints
│   │   ├── kyc.py                    # KYC verification endpoints
│   │   ├── badges.py                 # Badge endpoints
│   │   ├── subscription.py           # Subscription management endpoints
│   │   ├── dispute.py                # Dispute resolution endpoints
│   │   ├── admin.py                  # Admin dashboard endpoints
│   │   ├── dashboard.py              # User dashboard endpoints
│   │   ├── worker.py                 # Worker-specific endpoints
│   │   ├── files.py                  # File upload/download endpoints
│   │   ├── categories.py             # Category endpoints
│   │   ├── referral.py               # Referral system endpoints
│   │   ├── recent_activity.py        # Activity feed endpoints
│   │   ├── waitlist.py               # Waitlist endpoints
│   │   └── revenue.py                # Revenue reporting endpoints
│   │
│   ├── services/                     # Business logic layer
│   │   ├── auth_service.py           # Authentication & JWT handling
│   │   ├── user_service.py           # User operations & profile management
│   │   ├── job_service.py            # Job posting & search logic
│   │   ├── payment_service.py        # Payment processing & wallet management
│   │   ├── review_service.py         # Review & rating logic
│   │   ├── message_service.py        # Messaging logic
│   │   ├── notification_service.py   # Notification dispatch
│   │   ├── kyc_service.py            # KYC verification logic
│   │   ├── dispute_service.py        # Dispute resolution logic
│   │   ├── subscription_service.py   # Subscription management
│   │   ├── referral_service.py       # Referral reward logic
│   │   ├── admin_service.py          # Admin operations
│   │   ├── worker_service.py         # Worker profile operations
│   │   ├── badge_service.py          # Badge awarding logic
│   │   └── [others]                  # Additional services
│   │
│   ├── tasks/                        # Celery background tasks
│   │   ├── notifications.py          # Email & SMS notifications
│   │   ├── cleanup.py                # Database cleanup & maintenance
│   │   ├── payments.py               # Payment processing tasks
│   │   ├── waitlist.py               # Waitlist management tasks
│   │   └── newsletter.py             # Newsletter distribution
│   │
│   ├── utils/                        # Helper functions & utilities
│   │   ├── security.py               # Password hashing, JWT utilities
│   │   ├── validators.py             # Validation helpers
│   │   ├── email.py                  # Email sending utilities
│   │   ├── sms.py                    # SMS sending utilities (Twilio)
│   │   ├── file_handler.py           # File upload/storage logic
│   │   └── [others]                  # Additional utilities
│   │
│   ├── middlewares/                  # Custom middleware
│   │   ├── error_handler.py          # Global exception handling
│   │   └── rate_limiter.py           # Request rate limiting
│   │
│   └── dependencies/                 # FastAPI dependency injection
│       ├── application_fee.py        # Application fee calculation
│       ├── rate_limiter.py           # Rate limiting logic
│       ├── subscription.py           # Subscription validation
│       └── worker.py                 # Worker-specific dependencies
│
├── tests/                            # Test suite
│   ├── conftest.py                   # Pytest configuration & fixtures
│   ├── pytest.ini                    # Pytest settings
│   ├── test_all.py                   # Comprehensive integration tests
│   ├── test_journeys.py              # User journey/workflow tests
│   └── __init__.py
│
├── scripts/                          # Utility scripts
│   ├── init_db.py                    # Database initialization
│   ├── seed_db.py                    # Sample data generation
│   └── [others]                      # Additional scripts
│
├── install/                          # Installation & deployment configs
│   ├── jobconnect.service            # Systemd service file (Linux)
│   ├── setup_linux.sh                # Linux setup script
│   └── setup_windows.bat             # Windows setup script
│
├── alembic.ini                       # Alembic configuration
├── Dockerfile                        # Docker image definition
├── docker-compose.yml                # Multi-container Docker setup
├── docker-compose.prod.yml           # Production Docker configuration
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variables template
├── run_ssl.py                        # SSL/TLS server runner
└── README.md                         # This file
```

## 🚀 Prerequisites

- **Python 3.10+**
- **PostgreSQL 13+** (with replication support for read replicas)
- **Redis 6.2+** (for Celery message broker)
- **Docker & Docker Compose** (optional, for containerized setup)

### External Service Accounts
- **Paystack** - Payment processing (get credentials from paystack.com)
- **Twilio** - SMS notifications (get credentials from twilio.com)
- **SMTP Server** - Email notifications (Gmail, SendGrid, Mailgun, etc.)

## 🛠️ Installation & Setup

### Option 1: Docker Compose (Recommended)

1. **Clone the repository**
```bash
git clone https://github.com/port-seven/job-connect-backend.git
cd job-connect-backend
```

2. **Create environment file**
```bash
cp .env.example .env
# Edit .env with your configuration:
# - Database credentials
# - JWT secrets
# - Paystack keys
# - Twilio credentials
# - Email server settings
```

3. **Build and start containers**
```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`

**Database Replication:**
- Primary DB: `localhost:5432` (jobconnect)
- Read Replica: `localhost:5433` (jobconnect-read)
- Redis: `localhost:6379`

### Option 2: Local Development

1. **Clone and navigate to project**
```bash
git clone https://github.com/port-seven/job-connect-backend.git
cd job-connect-backend
```

2. **Create Python virtual environment**
```bash
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate           # Linux/macOS
# OR
.venv\Scripts\activate              # Windows
```

3. **Install dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**
```bash
# Create database schema and run migrations
alembic upgrade head

# (Optional) Seed database with sample data
python3 app/scripts/seed_db.py
```

6. **Start development server**
```bash
# Single terminal - FastAPI only
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Alternative: Run with SSL support
python3 run_ssl.py
```

7. **Start Celery worker (in another terminal)**
```bash
celery -A app.celery_worker.celery_app worker --loglevel=info
```

8. **(Optional) Start Celery beat scheduler**
```bash
celery -A app.celery_worker.celery_app beat --loglevel=info
```

## 📚 API Documentation

Once the server is running, interactive API documentation is available at:

- **Swagger UI** (interactive API explorer): http://localhost:8000/api/v1/docs
- **ReDoc** (API reference documentation): http://localhost:8000/api/v1/redoc
- **OpenAPI JSON schema**: http://localhost:8000/api/v1/openapi.json

### Complete API Endpoint Reference

#### **Authentication Router** (`/api/v1/auth`)
```
POST   /register              - Register new user
  Body: RegisterRequest {email, password, first_name, last_name, phone, role}
  Returns: UserOut
  Status: 201 Created

POST   /login                 - User login
  Body: LoginRequest {email, password}
  Returns: TokenResponse {access_token, refresh_token, token_type}

POST   /refresh               - Refresh access token
  Body: {refresh_token}
  Returns: TokenResponse

POST   /logout                - Logout user (blacklist token)
  Returns: {message}

POST   /request-otp           - Request OTP for email verification
  Body: VerifyAccountRequest {email}
  Returns: {message}

POST   /verify-otp            - Verify email with OTP
  Body: VerifyOTPRequest {email, otp_code}
  Returns: VerifyOTPResponse

POST   /forgot-password       - Request password reset
  Body: ForgotPasswordRequest {email}
  Returns: {message}

POST   /reset-password        - Reset password with token
  Body: ResetPasswordRequest {token, new_password}
  Returns: {message}

POST   /resend-otp            - Resend OTP
  Body: ResendOTPRequest {email}
  Returns: {message}
```

---

#### **Users Router** (`/api/v1/users`)
```
GET    /me                    - Get current user profile
  Returns: UserOut
  Auth: Required

PUT    /me                    - Update current user profile
  Body: UserUpdate {...}
  Returns: UserOut
  Auth: Required

PUT    /me/switch-role        - Switch between Employer/Worker roles
  Body: UserRoleSwitch {role}
  Returns: UserOut
  Auth: Required

POST   /me/avatar             - Upload profile avatar
  Body: multipart/form-data {file}
  Returns: {avatar_url}
  Auth: Required
  Max Size: MAX_UPLOAD_SIZE

GET    /me/wallet             - Get wallet balance
  Returns: {wallet_balance}
  Auth: Required

GET    /workers               - List all workers (employers view)
  Query: skip, limit
  Returns: List[UserOut]
  Auth: Required (Employer/Admin)

GET    /{user_id}             - Get user profile by ID
  Returns: UserOut
  Auth: Optional

GET    /{user_id}/wallet      - Get user wallet (admin view)
  Returns: {wallet_balance}
  Auth: Required (Admin)

POST   /{user_id}/wallet/fund - Fund user wallet (admin)
  Body: WalletFundingRequest {amount}
  Returns: {wallet_balance, transaction_id}
  Auth: Required (Admin)
```

---

#### **Jobs Router** (`/api/v1/jobs`)
```
POST   /                      - Create new job (employer only)
  Body: JobCreate {title, description, budget, location, location_type, category_id, ...}
  Returns: JobInDB
  Status: 201 Created
  Auth: Required (Employer)

GET    /                      - List jobs with filters
  Query: status, location_type, category, location, skip, limit
  Returns: List[JobInDB]
  Auth: Optional

GET    /{job_id}              - Get job details
  Returns: JobInDB | JobWithApplications (for employer)
  Auth: Optional

PUT    /{job_id}              - Update job (employer only)
  Body: JobUpdate {...}
  Returns: JobInDB
  Auth: Required (Employer)

DELETE /{job_id}              - Cancel/delete job
  Returns: {message}
  Auth: Required (Employer/Admin)

GET    /{job_id}/applications - List job applications
  Query: status, skip, limit
  Returns: List[JobApplicationInDB]
  Auth: Required (Employer)

POST   /{job_id}/apply        - Apply for job (worker only)
  Body: JobApplicationCreate {cover_letter, proposed_budget}
  Returns: JobApplicationInDB
  Status: 201 Created
  Auth: Required (Worker)

PUT    /{job_id}/applications/{app_id}/accept - Accept application
  Returns: JobApplicationInDB
  Auth: Required (Employer)

PUT    /{job_id}/applications/{app_id}/reject - Reject application
  Returns: JobApplicationInDB
  Auth: Required (Employer)

PUT    /{job_id}/applications/{app_id}/withdraw - Withdraw application
  Returns: JobApplicationInDB
  Auth: Required (Worker)
```

---

#### **Payments Router** (`/api/v1/payments`)
```
POST   /initialize            - Initialize wallet funding payment
  Body: TransactionCreate {amount}
  Returns: InitializePaymentResponse {authorization_url, access_code, reference}
  Auth: Required

POST   /callback              - Paystack webhook callback
  Body: {event, data}
  Returns: {status: "success"}
  No Auth (Webhook)

POST   /pay-worker            - Pay worker from wallet (employer)
  Body: {worker_id, amount}
  Returns: {transaction_id, status}
  Auth: Required (Employer)

GET    /history               - Get payment history
  Query: status, type, skip, limit
  Returns: List[PaymentResponse]
  Auth: Required

GET    /wallet-balance        - Get wallet balance
  Returns: {wallet_balance, currency}
  Auth: Required

POST   /withdraw              - Withdraw funds to bank
  Body: {amount, bank_code, account_number}
  Returns: {withdrawal_id, status}
  Auth: Required

GET    /{payment_id}          - Get payment details
  Returns: PaymentResponse
  Auth: Required
```

---

#### **Reviews Router** (`/api/v1/reviews`)
```
POST   /                      - Create review
  Body: ReviewCreate {reviewee_id, job_id, rating, comment}
  Returns: ReviewInDB
  Status: 201 Created
  Auth: Required

GET    /user/{user_id}        - Get reviews for user
  Query: skip, limit
  Returns: List[ReviewInDB]
  Auth: Optional

GET    /user/{user_id}/stats  - Get user review statistics
  Returns: ReviewStats {average_rating, total_reviews, rating_distribution}
  Auth: Optional

GET    /job/{job_id}          - Get reviews for job
  Query: skip, limit
  Returns: List[ReviewInDB]
  Auth: Optional

PUT    /{review_id}           - Update review
  Body: ReviewUpdate {rating, comment}
  Returns: ReviewInDB
  Auth: Required (Reviewer)

DELETE /{review_id}           - Delete review
  Returns: {message}
  Auth: Required (Reviewer/Admin)
```

---

#### **Messages Router** (`/api/v1/messages`)
```
WS     /ws/{user_id}         - WebSocket connection for messaging
  Query: token (JWT)
  Message Format: {type, receiver_id, content, message_type}
  Auth: Required (WebSocket)

POST   /                      - Send message (HTTP fallback)
  Body: MessageCreate {receiver_id, content, message_type}
  Returns: MessageInDB
  Status: 201 Created
  Auth: Required

GET    /{user_id}             - Get conversation with user
  Query: skip, limit
  Returns: List[MessageInDB]
  Auth: Required

GET    /conversations         - Get all conversations
  Query: skip, limit
  Returns: List[Conversation]
  Auth: Required

PUT    /{message_id}/read     - Mark message as read
  Returns: MessageInDB
  Auth: Required

GET    /unread/count          - Get unread message count
  Returns: {unread_count}
  Auth: Required

DELETE /{message_id}          - Delete message
  Returns: {message}
  Auth: Required (Sender/Admin)
```

---

#### **KYC Router** (`/api/v1/kyc`)
```
POST   /submit                - Submit KYC documents
  Body: multipart/form-data {document_type, document, selfie}
  Returns: KYCSubmission
  Status: 201 Created
  Auth: Required

GET    /status                - Get KYC verification status
  Returns: KYCStatus {status, notes, verified_at}
  Auth: Required

GET    /submissions/{submission_id} - Get submission details
  Returns: KYCSubmission
  Auth: Required (Submitter/Admin)

POST   /submissions/{submission_id}/verify - Verify KYC (admin)
  Body: KYCVerification {status, notes}
  Returns: KYCVerification
  Auth: Required (Admin)

GET    /list                  - List pending KYC submissions (admin)
  Query: status, skip, limit
  Returns: List[KYCSubmission]
  Auth: Required (Admin)

DELETE /submissions/{submission_id} - Delete submission
  Returns: {message}
  Auth: Required (Admin)
```

---

#### **Badges Router** (`/api/v1/badges`)
```
POST   /                      - Create badge (admin only)
  Body: BadgeCreate {name, description, image_url, criteria}
  Returns: BadgeInDB
  Status: 201 Created
  Auth: Required (Admin)

GET    /                      - List all badges
  Query: skip, limit
  Returns: List[BadgeInDB]
  Auth: Optional

POST   /{badge_id}/award/{user_id} - Award badge to user (admin)
  Returns: UserBadgeInDB
  Auth: Required (Admin)

GET    /user/{user_id}        - Get user badges
  Returns: List[UserBadgeInDB]
  Auth: Optional

DELETE /{badge_id}/revoke/{user_id} - Revoke badge (admin)
  Returns: {message}
  Auth: Required (Admin)
```

---

#### **Subscriptions Router** (`/api/v1/subscriptions`)
```
POST   /plans                 - Create plan (admin)
  Body: SubscriptionPlanCreate {name, price, features}
  Returns: SubscriptionPlanInDB
  Status: 201 Created
  Auth: Required (Admin)

GET    /plans                 - List subscription plans
  Returns: List[SubscriptionPlanInDB]
  Auth: Optional

PUT    /plans/{plan_id}       - Update plan (admin)
  Body: SubscriptionPlanUpdate {...}
  Returns: SubscriptionPlanInDB
  Auth: Required (Admin)

DELETE /plans/{plan_id}       - Delete plan (admin)
  Returns: {message}
  Auth: Required (Admin)

POST   /subscribe/{plan_id}   - Subscribe user to plan
  Returns: {message, subscription_expires_at}
  Auth: Required

GET    /status                - Get current subscription status
  Returns: {plan, expires_at, features}
  Auth: Required

POST   /cancel                - Cancel subscription
  Returns: {message}
  Auth: Required
```

---

#### **Disputes Router** (`/api/v1/disputes`)
```
POST   /                      - Create dispute
  Body: DisputeCreate {job_id, reason}
  Returns: DisputeInDB
  Status: 201 Created
  Auth: Required

GET    /my-disputes           - Get user's disputes
  Returns: List[DisputeInDB]
  Auth: Required

GET    /{dispute_id}          - Get dispute details
  Returns: DisputeDetails
  Auth: Required (Parties/Admin)

PUT    /{dispute_id}          - Update dispute (admin resolution)
  Body: DisputeUpdate {status, resolution}
  Returns: DisputeInDB
  Auth: Required (Admin)

GET    /                      - List disputes (admin)
  Query: status, skip, limit
  Returns: List[DisputeInDB]
  Auth: Required (Admin)
```

---

#### **Admin Router** (`/api/v1/admin`)
```
GET    /dashboard             - Admin dashboard statistics
  Returns: DashboardStats {total_users, total_jobs, total_revenue, ...}
  Auth: Required (Admin)

GET    /users                 - List all users (filtered)
  Query: role, is_verified, is_active, kyc_status, skip, limit
  Returns: UserList
  Auth: Required (Admin)

PUT    /users/{user_id}       - Update user (admin)
  Body: UserUpdate {...}
  Returns: UserOut
  Auth: Required (Admin)

POST   /users/{user_id}/ban   - Ban user
  Returns: {message}
  Auth: Required (Admin)

POST   /users/{user_id}/unban - Unban user
  Returns: {message}
  Auth: Required (Admin)

GET    /jobs                  - List all jobs (admin view)
  Query: status, skip, limit
  Returns: AdminJobList
  Auth: Required (Admin)

POST   /jobs/{job_id}/feature - Feature job (admin)
  Returns: {message}
  Auth: Required (Admin)

GET    /disputes              - List disputes
  Query: status, skip, limit
  Returns: DisputeList
  Auth: Required (Admin)

PUT    /disputes/{dispute_id}/resolve - Resolve dispute
  Body: AdminDisputeResolution {resolution, notes}
  Returns: DisputeDetails
  Auth: Required (Admin)

GET    /reviews               - List reviews (admin moderation)
  Query: skip, limit
  Returns: ReviewList
  Auth: Required (Admin)

DELETE /reviews/{review_id}   - Remove review
  Returns: {message}
  Auth: Required (Admin)

GET    /revenue               - Get revenue report
  Query: start_date, end_date
  Returns: RevenueReport
  Auth: Required (Admin)

POST   /kyc/{submission_id}/verify - Verify KYC
  Body: KYCVerification {status, notes}
  Returns: KYCVerification
  Auth: Required (Admin)

GET    /kyc/pending           - List pending KYC submissions
  Returns: List[KYCSubmission]
  Auth: Required (Admin)

POST   /wallet/{user_id}/fund - Fund user wallet
  Body: {amount}
  Returns: {balance, transaction_id}
  Auth: Required (Admin)

POST   /notifications/send    - Send system notification
  Body: {user_id, message, type}
  Returns: {message}
  Auth: Required (Admin)
```

---

#### **Files Router** (`/api/v1/files`)
```
POST   /upload                - Upload file
  Body: multipart/form-data {file, category, reference_id, reference_type}
  Returns: FileInDB
  Status: 201 Created
  Auth: Required
  Max Size: MAX_UPLOAD_SIZE

GET    /{file_id}             - Get file info
  Returns: FileInDB
  Auth: Required

GET    /{file_id}/download    - Download file
  Returns: File (binary)
  Auth: Required (Owner/Admin)

DELETE /{file_id}             - Delete file
  Returns: {message}
  Auth: Required (Owner/Admin)

GET    /user/{user_id}        - List user files
  Query: category, skip, limit
  Returns: List[FileInDB]
  Auth: Required (User/Admin)
```

---

#### **Worker Router** (`/api/v1/worker`)
```
GET    /profile               - Get worker profile
  Returns: UserProfile
  Auth: Required (Worker)

PUT    /profile               - Update worker profile
  Body: WorkerProfileUpdate {about_me, services_offered, recent_works}
  Returns: UserProfile
  Auth: Required (Worker)

POST   /services              - Add service offered
  Body: {service_name}
  Returns: UserService
  Auth: Required (Worker)

POST   /recent-work           - Add recent work/portfolio item
  Body: {description, image_url}
  Returns: RecentWork
  Auth: Required (Worker)

DELETE /services/{service_id} - Remove service
  Returns: {message}
  Auth: Required (Worker)

DELETE /recent-work/{work_id} - Remove portfolio item
  Returns: {message}
  Auth: Required (Worker)
```

---

#### **Dashboard Router** (`/api/v1/dashboard`)
```
GET    /                      - Get user dashboard data
  Returns: DashboardData {jobs_posted, jobs_applied, active_jobs, earnings, ...}
  Auth: Required
```

---

#### **Notifications Router** (`/api/v1/notifications`)
```
POST   /                      - Create notification (internal)
  Body: NotificationCreate {user_id, message}
  Returns: Notification
  Auth: Required

GET    /                      - Get user notifications
  Query: skip, limit
  Returns: List[Notification]
  Auth: Required

GET    /{notification_id}     - Get notification details
  Returns: Notification
  Auth: Required

PUT    /{notification_id}/read - Mark as read
  Returns: Notification
  Auth: Required

DELETE /{notification_id}     - Delete notification
  Returns: {message}
  Auth: Required

POST   /read-all              - Mark all as read
  Returns: {message}
  Auth: Required
```

---

#### **Referrals Router** (`/api/v1/referrals`)
```
GET    /code                  - Get referral code
  Returns: {referral_code}
  Auth: Required

GET    /                      - Get referrals (earned)
  Returns: List[Referral]
  Auth: Required

GET    /stats                 - Get referral statistics
  Returns: {total_referrals, completed_referrals, total_earned}
  Auth: Required

POST   /settings              - Create referral settings (admin)
  Body: ReferralSettingsCreate {user_role, reward_amount}
  Returns: ReferralSettingsInDB
  Auth: Required (Admin)

GET    /settings              - Get referral settings
  Returns: List[ReferralSettingsInDB]
  Auth: Optional
```

---

#### **Categories Router** (`/api/v1/categories`)
```
GET    /                      - List job categories
  Query: skip, limit
  Returns: List[CategoryInDB]
  Auth: Optional
```

---

#### **Waitlist Router** (`/api/v1`)
```
POST   /waitlist              - Add to waitlist
  Body: WaitlistCreate {first_name, last_name, email, user_type, location, newsletter}
  Returns: Waitlist
  Status: 201 Created

GET    /waitlist              - List waitlist (admin)
  Returns: List[Waitlist]
  Auth: Required (Admin)

DELETE /waitlist/{email}      - Remove from waitlist
  Returns: {message}
  Auth: Required (Admin)

GET    /countdown             - Get launch countdown
  Returns: Countdown {launch_date}
```

---

#### **Recent Activity Router** (`/api/v1`)
```
GET    /users/me/recent-activity - Get user's recent activities
  Query: skip, limit
  Returns: List[RecentActivity]
  Auth: Required

GET    /recent-activity       - Get all activities (admin)
  Query: skip, limit
  Returns: List[RecentActivity]
  Auth: Required (Admin)
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_all.py

# Run specific test function
pytest tests/test_all.py::test_user_registration

# Run tests with verbose output
pytest -v

# Run tests in parallel
pytest -n auto
```

## 🔧 Services & Business Logic Layer

The `app/services/` directory contains business logic that handles:
- Data validation and transformation
- Database operations
- Third-party API interactions
- Complex workflows

### Service Classes

#### **AuthService** (`auth_service.py`)
Handles user authentication and account management
- `register_user()` - Create new user with validation
- `login_user()` - Authenticate and issue JWT tokens
- `verify_email()` - Email verification with OTP
- `request_password_reset()` - Password recovery flow
- `reset_password()` - Change password with token
- `refresh_access_token()` - Issue new access token
- `logout_user()` - Blacklist JWT token

#### **UserService** (`user_service.py`)
User profile and account management
- `get_user()` - Retrieve user by ID
- `update_user()` - Update user information
- `switch_user_role()` - Toggle between Employer/Worker
- `upload_avatar()` - Save profile picture
- `get_wallet_balance()` - Check user funds
- `fund_wallet()` - Add funds to wallet
- `withdraw_funds()` - Withdraw to bank account
- `update_reputation()` - Calculate and update reputation score

#### **JobService** (`job_service.py`)
Job posting and search operations
- `create_job()` - Create new job posting
- `get_jobs()` - Search with filtering (status, location, category)
- `get_job_by_id()` - Retrieve specific job
- `update_job()` - Modify job details
- `delete_job()` - Cancel job posting
- `list_user_jobs()` - Jobs posted by employer
- `mark_job_complete()` - Finalize job

#### **JobApplicationService** (within JobService)
- `create_application()` - Apply for job with fee handling
- `get_applications()` - List job applications
- `accept_application()` - Approve application
- `reject_application()` - Decline application
- `withdraw_application()` - Worker withdrawal

#### **PaymentService** (`payment_service.py`)
Payment processing and financial management
- `initialize_payment()` - Start payment flow
- `verify_payment()` - Validate Paystack callback
- `create_customer()` - Register in Paystack
- `get_payment_history()` - Transaction records
- `process_wallet_funding()` - Deposit to wallet
- `process_withdrawal()` - Cash out to bank
- `calculate_commission()` - Platform fee computation

#### **TransactionService** (`transaction_service.py`)
Low-level transaction tracking
- `create_transaction()` - Record transaction
- `initialize_payment()` - Paystack initialization
- `verify_payment()` - Webhook verification
- `get_transaction_history()` - User transactions

#### **EscrowService** (within PaymentService)
Escrow fund management
- `create_escrow()` - Fund escrow for job
- `release_escrow()` - Release funds to worker
- `hold_escrow()` - Hold pending dispute
- `refund_escrow()` - Return to employer
- `calculate_commission()` - 10% fee calculation

#### **ReviewService** (`review_service.py`)
Rating and review management
- `create_review()` - Submit rating/feedback
- `get_user_reviews()` - Get reviews received
- `get_user_review_stats()` - Rating statistics
- `get_job_reviews()` - Reviews for specific job
- `update_reputation_from_reviews()` - Calculate aggregate score

#### **DisputeService** (`dispute_service.py`)
Conflict resolution
- `create_dispute()` - Open dispute on job
- `get_disputes_for_user()` - User disputes
- `get_dispute_by_id()` - Dispute details
- `update_dispute()` - Admin resolution
- `resolve_dispute()` - Finalize and release escrow
- `get_all_disputes()` - List for admin

#### **MessageService** (`message_service.py`)
In-app messaging
- `create_message()` - Save message
- `get_conversation()` - Retrieve message history
- `get_all_conversations()` - User's chats
- `mark_as_read()` - Read status
- `delete_message()` - Remove message
- `handle_call_message()` - WebSocket signaling

#### **NotificationService** (`notification_service.py`)
User notifications
- `create_notification()` - Record notification
- `get_user_notifications()` - List user's notifications
- `get_notification_by_id()` - Notification details
- `mark_as_read()` - Read status
- `mark_all_as_read()` - Bulk read
- `delete_notification()` - Remove notification

#### **KYCService** (`kyc_service.py`)
Know Your Customer verification
- `submit_verification()` - Upload documents
- `get_verification_status()` - Check status
- `verify_submission()` - Admin approval
- `get_pending_submissions()` - Admin queue
- `verify_with_external_api()` - Integration (NIMC, etc.)

#### **SubscriptionService** (`subscription_service.py`)
Subscription plan management
- `create_plan()` - Define subscription tier
- `get_all_plans()` - List available plans
- `update_plan()` - Modify plan
- `subscribe_user_to_plan()` - Assign plan to user
- `get_user_subscription_status()` - Current plan info
- `check_subscription_active()` - Validate subscription

#### **BadgeService** (`badge_service.py`)
Achievement badges
- `create_badge()` - Define badge criteria
- `get_all_badges()` - List badges
- `award_badge()` - Assign badge to user
- `get_user_badges()` - User's badges
- `revoke_badge()` - Remove badge
- `check_badge_criteria()` - Automatic award logic

#### **FileService** (`file_service.py`)
File upload and management
- `upload_file()` - Save file with validation
- `get_file()` - Retrieve file info
- `get_file_by_reference()` - Find files by related entity
- `delete_file()` - Remove file
- `generate_download_url()` - Get file URL
- `validate_file_type()` - Check MIME type
- `get_allowed_types()` - Category-specific validation

#### **AdminService** (`admin_service.py`)
Admin operations and reporting
- `get_dashboard_stats()` - Overall platform metrics
- `list_users()` - User management
- `ban_user()` - Account suspension
- `unban_user()` - Reinstate account
- `get_revenue_report()` - Financial analytics
- `moderate_content()` - Review management
- `send_system_notification()` - Broadcast message

#### **WorkerService** (`worker_service.py`)
Worker-specific features
- `get_user_profile()` - Worker profile
- `update_user_profile()` - Profile modification
- `add_portfolio_item()` - Recent work
- `add_service()` - Service offering
- `get_recommended_jobs()` - Job suggestions

#### **ReferralService** (`referral_service.py`)
Referral program
- `generate_referral_code()` - Create unique code
- `process_referral()` - Mark referral complete
- `calculate_reward()` - Determine reward amount
- `award_reward()` - Add funds to wallet
- `get_referrals_by_user()` - User's referrals
- `get_referral_settings()` - Admin settings

#### **NotificationManager** (`tasks/notifications.py`)
Background email/SMS notifications
- `send_notification()` - Email dispatch
- `send_sms_notification()` - Twilio SMS
- `send_verification_email()` - Account verification
- `send_payment_confirmation()` - Payment receipt
- `send_dispute_notice()` - Dispute notification

#### **Additional Services**
- **CategoryService** - Job category management
- **CountdownService** - Launch countdown tracking
- **NewsletterService** - Email campaign management
- **OTPService** - One-time password generation
- **WaitlistService** - Pre-launch user list
- **RecentActivityService** - Activity logging

---

## 📊 Pydantic Schemas (Request/Response Models)

Schemas provide data validation and serialization in `app/schemas/`

### Core Schemas

#### **Auth Schemas** (`auth.py`)
```python
RegisterRequest
  - email: str
  - password: str
  - first_name: str
  - last_name: str
  - phone: str
  - role: UserRole (optional)

LoginRequest
  - email: str
  - password: str

TokenResponse
  - access_token: str
  - refresh_token: str
  - token_type: str = "bearer"

ForgotPasswordRequest
  - email: str

ResetPasswordRequest
  - token: str
  - new_password: str

VerifyOTPRequest
  - email: str
  - otp_code: str

VerifyOTPResponse
  - message: str
  - is_verified: bool
```

#### **User Schemas** (`user.py`)
```python
UserCreate
  - email: str
  - password: str
  - first_name: str
  - last_name: str
  - phone: str
  - role: UserRole

UserOut
  - id: int
  - email: str
  - first_name: str
  - last_name: str
  - phone: str
  - role: UserRole
  - is_verified: bool
  - is_kyc_verified: bool
  - avatar_url: Optional[str]
  - reputation_score: float
  - wallet_balance: float
  - created_at: datetime
  - updated_at: datetime

UserUpdate
  - first_name: Optional[str]
  - last_name: Optional[str]
  - phone: Optional[str]
  - avatar_url: Optional[str]
  - about_me: Optional[str]
  - location: Optional[str]

UserRoleSwitch
  - role: UserRole

UserProfile
  - user: UserOut
  - recent_works: List[RecentWork]
  - services_offered: List[UserService]
  - badges: List[UserBadgeInDB]
```

#### **Job Schemas** (`job.py`)
```python
JobCreate
  - title: str
  - description: str
  - requirements: Optional[str]
  - budget: float
  - location: str
  - location_type: JobLocationType
  - job_type: Optional[JobType]
  - category_id: int
  - tags: Optional[List[str]]

JobUpdate
  - title: Optional[str]
  - description: Optional[str]
  - budget: Optional[float]
  - status: Optional[JobStatus]

JobInDB
  - id: int
  - title: str
  - description: str
  - budget: float
  - location: str
  - location_type: JobLocationType
  - status: JobStatus
  - employer_id: int
  - worker_id: Optional[int]
  - category_id: int
  - is_high_value: bool
  - escrow_required: bool
  - created_at: datetime
  - updated_at: datetime

JobWithApplicationCount
  - job: JobInDB
  - application_count: int

JobWithApplications
  - job: JobInDB
  - applications: List[JobApplicationInDB]
```

#### **Payment Schemas** (`payment.py`)
```python
PaymentCreate
  - user_id: int
  - job_id: Optional[int]
  - amount: float
  - payment_type: PaymentType
  - description: Optional[str]

PaymentResponse
  - id: int
  - user_id: int
  - amount: float
  - payment_type: PaymentType
  - status: PaymentStatus
  - created_at: datetime
  - completed_at: Optional[datetime]

InitializePaymentResponse
  - authorization_url: str
  - access_code: str
  - reference: str

TransactionCreate
  - amount: Decimal
  - description: Optional[str]
```

#### **Review Schemas** (`review.py`)
```python
ReviewCreate
  - reviewee_id: int
  - job_id: int
  - rating: float (1-5)
  - comment: str (min 10 chars)

ReviewInDB
  - id: int
  - reviewer_id: int
  - reviewee_id: int
  - job_id: int
  - rating: float
  - comment: str
  - created_at: datetime

ReviewStats
  - average_rating: float
  - total_reviews: int
  - rating_distribution: Dict[int, int]
```

#### **Job Application Schemas** (`job_application.py`)
```python
JobApplicationCreate
  - cover_letter: str
  - proposed_budget: float
  - payment_required: Optional[bool]

JobApplicationInDB
  - id: int
  - job_id: int
  - worker_id: int
  - cover_letter: str
  - proposed_budget: float
  - status: ApplicationStatus
  - created_at: datetime

JobApplicationStatusUpdate
  - status: ApplicationStatus
```

#### **Message Schemas** (`message.py`)
```python
MessageCreate
  - receiver_id: int
  - content: str
  - message_type: Optional[MessageType]

MessageInDB
  - id: int
  - sender_id: int
  - receiver_id: int
  - content: str
  - is_read: bool
  - created_at: datetime

Conversation
  - user_id: int
  - first_name: str
  - last_name: str
  - last_message: str
  - last_message_time: datetime
  - unread_count: int
```

#### **KYC Schemas** (`kyc.py`)
```python
KYCSubmission
  - id: int
  - user_id: int
  - document_type: str
  - status: str
  - notes: Optional[str]
  - verified_at: Optional[datetime]

KYCVerification
  - id: int
  - status: str
  - notes: str
  - verified_at: datetime

KYCStatus
  - status: str
  - is_verified: bool
  - verified_at: Optional[datetime]
  - notes: Optional[str]
```

#### **Badge Schemas** (`badge.py`)
```python
BadgeCreate
  - name: str
  - description: str
  - image_url: str
  - criteria: str

BadgeInDB
  - id: int
  - name: str
  - description: str
  - image_url: str

UserBadgeInDB
  - id: int
  - user_id: int
  - badge_id: int
  - badge: BadgeInDB
  - awarded_at: datetime
```

#### **Subscription Schemas** (`subscription.py`)
```python
SubscriptionPlanCreate
  - name: str
  - price: float
  - features: Dict[str, Any]

SubscriptionPlanUpdate
  - name: Optional[str]
  - price: Optional[float]
  - features: Optional[Dict]

SubscriptionPlanInDB
  - id: int
  - name: str
  - price: float
  - features: Dict
```

#### **Dispute Schemas** (`dispute.py`)
```python
DisputeCreate
  - job_id: int
  - reason: str

DisputeUpdate
  - status: DisputeStatus
  - resolution: str

DisputeInDB
  - id: int
  - job_id: int
  - claimant_id: int
  - defendant_id: int
  - reason: str
  - status: DisputeStatus

DisputeDetails
  - dispute: DisputeInDB
  - job: JobInDB
  - claimant: UserOut
  - defendant: UserOut
```

#### **File Schemas** (`file.py`)
```python
FileInDB
  - id: int
  - filename: str
  - original_filename: str
  - file_path: str
  - file_type: str
  - file_size: int
  - category: str
  - user_id: int
  - created_at: datetime
```

#### **Notification Schemas** (`notification.py`)
```python
NotificationCreate
  - user_id: int
  - message: str

Notification
  - id: int
  - user_id: int
  - message: str
  - read: bool
  - created_at: datetime
```

#### **Admin Schemas** (`admin.py`)
```python
DashboardStats
  - total_users: int
  - total_employers: int
  - total_workers: int
  - total_jobs: int
  - open_jobs: int
  - completed_jobs: int
  - total_revenue: float
  - total_escrow: float
  - active_disputes: int
  - pending_kyc: int
  - new_users_today: int

UserList
  - total: int
  - items: List[UserOut]

AdminJobList
  - total: int
  - items: List[JobInDB]
```

#### **Other Key Schemas**
- **ReferralSettings** - Referral configuration
- **Waitlist** - Waitlist entry
- **RecentActivity** - Activity log entry
- **TransactionCreate** - Transaction request
- **Countdown** - Launch countdown data

---

## 🔐 Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jobconnect
READ_REPLICA_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5433/jobconnect
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jobconnect_test

# JWT Settings
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
JWT_REFRESH_SECRET_KEY=your-super-secret-refresh-key-change-this
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Paystack Payment Gateway
PAYSTACK_SECRET_KEY=sk_test_your_paystack_secret_key
PAYSTACK_PUBLIC_KEY=pk_test_your_paystack_public_key
PAYSTACK_BASE_URL=https://api.paystack.co

# Email Configuration (SMTP)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_FROM=noreply@jobconnect.com
MAIL_SENDER_NAME=JobConnect

# Twilio SMS
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1234567890

# File Storage
UPLOAD_DIR=storage/uploads
MAX_UPLOAD_SIZE=10485760  # 10MB in bytes

# KYC Verification
UVERIFY_API_KEY=your_uverify_api_key
UVERIFY_API_URL=https://api.uverify.com

# NIMC Verification
NIMC_API_KEY=your_nimc_api_key
NIMC_API_URL=https://api.nimc.com

# Redis (Celery Broker)
REDIS_URL=redis://localhost:6379/0

# CORS & Frontend
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:3001","https://jobconnect.com"]
API_BASE_URL=http://localhost:8000

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Application Settings
DEBUG=False
TESTING=False
API_V1_PREFIX=/api/v1
PROJECT_NAME=JobConnect
VERSION=1.0.0
DEFAULT_ADMIN_EMAIL=admin@jobconnect.com
DEFAULT_ADMIN_PASSWORD=SecureAdminPass123!

# SSL/TLS (Optional)
ENABLE_SSL=False
SSL_CERT_PATH=/path/to/cert.pem
SSL_KEY_PATH=/path/to/key.pem
```

## 📈 Complete Database Schema

### Model Details & Relationships

#### **User** (`app/models/user.py`)
Central user model supporting all three roles (Admin, Employer, Worker)

**Fields:**
- `id` (PK) - Primary key
- `email` - Unique email, index
- `phone` - Unique phone, index
- `hashed_password` - Bcrypt hashed password
- `first_name`, `last_name` - User name
- `role` - Enum (ADMIN, EMPLOYER, WORKER)
- `is_active` - Account status
- `is_verified` - Email verification status
- `is_kyc_verified` - KYC approval status
- `avatar_url` - Profile picture URL
- `reputation_score` - Float (0-5 stars)
- `wallet_balance` - Available funds
- `free_applications_used` - Tracks free job applications
- `subscription_status` - Active subscription flag
- `subscription_expiry` - Subscription renewal date
- `subscription_plan_id` - FK to SubscriptionPlan
- `paystack_customer_code` - Paystack integration ID
- `failed_login_attempts` - For security lockout
- `lockout_until` - Account lockout timestamp
- `referral_code` - Unique referral code
- `referred_by` - FK to User (self-referential)
- `location` - User location
- `about_me` - Bio/description (Text)
- `service_category` - Preferred job category
- `id_type`, `id_number`, `id_image_url` - KYC document info
- `selfie_image_url` - KYC selfie
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `jobs_posted` ↔ Job (employer_id)
- `jobs_worked` ↔ Job (worker_id)
- `jobs_applied` ↔ JobApplication
- `files` ↔ File (one-to-many)
- `reviews_given` ↔ Review (reviewer_id)
- `reviews_received` ↔ Review (reviewee_id)
- `badges` ↔ UserBadge
- `sent_messages` ↔ Message (sender_id)
- `received_messages` ↔ Message (receiver_id)
- `kyc_submissions` ↔ KYCSubmission
- `payments` ↔ Payment
- `employer_escrows` ↔ EscrowTransaction (employer_id)
- `worker_escrows` ↔ EscrowTransaction (worker_id)
- `disputes_claimed` ↔ Dispute (claimant_id)
- `disputes_defended` ↔ Dispute (defendant_id)
- `disputes_resolved` ↔ Dispute (resolved_by_admin_id)
- `notifications` ↔ Notification
- `subscription_plan` ↔ SubscriptionPlan
- `rewards` ↔ Reward
- `recent_works` ↔ RecentWork
- `services_offered` ↔ UserService
- `recent_activities` ↔ RecentActivity

---

#### **Job** (`app/models/job.py`)
Job posting with full lifecycle management

**Enums:**
- `JobStatus` - DRAFT, OPEN, IN_PROGRESS, COMPLETED, CANCELLED, DISPUTED
- `JobLocationType` - REMOTE, ONSITE, HYBRID
- `JobType` - ONE_TIME, PART_TIME, FULL_TIME

**Fields:**
- `id` (PK)
- `title` - Job title (200 chars max)
- `description` - Full job description
- `requirements` - Required skills/qualifications
- `budget` - Job payment amount
- `location` - Geographic location
- `location_type` - Enum (remote, onsite, hybrid)
- `job_type` - Enum for employment type
- `tags` - JSONB for flexible categorization
- `status` - Current job status
- `employer_id` - FK to User (job creator)
- `worker_id` - FK to User (assigned worker)
- `category_id` - FK to Category
- `is_high_value` - Flag for escrow requirement
- `escrow_required` - Boolean
- `commission_rate` - Platform fee (0.10 = 10%)
- `worker_completed` - Job completion flag
- `employer_completed` - Acceptance flag
- `completed_at`, `created_at`, `updated_at` - Timestamps

**Relationships:**
- `employer` ↔ User
- `worker` ↔ User
- `category` ↔ Category
- `applications` ↔ JobApplication (one-to-many)
- `payments` ↔ Payment
- `escrow_transactions` ↔ EscrowTransaction
- `reviews` ↔ Review
- `disputes` ↔ Dispute
- `attachments` ↔ File (job_attachment reference)

---

#### **JobApplication** (`app/models/job_application.py`)
Worker applications for job postings

**Enums:**
- `ApplicationStatus` - PENDING, REVIEWING, ACCEPTED, REJECTED, WITHDRAWN

**Fields:**
- `id` (PK)
- `job_id` - FK to Job
- `worker_id` - FK to User
- `cover_letter` - Application message (Text)
- `proposed_budget` - Worker's offered price
- `status` - Application status
- `payment_required` - Boolean
- `payment_id` - FK to Payment (application fee)
- `payment_status` - PaymentStatus enum
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `job` ↔ Job
- `worker` ↔ User
- `payment` ↔ Payment

---

#### **Payment** (`app/models/payment.py`)
All financial transactions in the system

**Enums:**
- `PaymentType` - SUBSCRIPTION, WALLET_FUNDING, APPLICATION_FEE, ESCROW_PAYMENT, ESCROW_RELEASE, COMMISSION
- `PaymentStatus` - PENDING, PROCESSING, COMPLETED, FAILED, REFUNDED, HELD

**Fields:**
- `id` (PK)
- `user_id` - FK to User
- `job_id` - FK to Job (nullable)
- `amount` - Transaction amount
- `payment_type` - Enum
- `status` - Payment status
- `paystack_reference` - External payment ID (unique)
- `virtual_account_number` - For dedicated accounts
- `commission_amount` - Platform fee
- `description` - Payment description
- `payment_metadata` - JSON for additional data
- `created_at`, `updated_at`, `completed_at` - Timestamps

**Relationships:**
- `user` ↔ User
- `job` ↔ Job
- `job_application` ↔ JobApplication
- `escrow_payments` ↔ EscrowTransaction
- `escrow_releases` ↔ EscrowTransaction

---

#### **EscrowTransaction** (`app/models/escrow_transaction.py`)
Safe fund holding for high-value jobs

**Enums:**
- `EscrowStatus` - FUNDED, PENDING, RELEASED, WITHHELD, REFUNDED, DISPUTED

**Fields:**
- `id` (PK)
- `job_id` - FK to Job
- `employer_id` - FK to User
- `worker_id` - FK to User
- `amount` - Total escrow amount
- `commission_rate` - Platform fee rate
- `commission_amount` - Calculated commission
- `net_amount` - Amount after commission
- `status` - Escrow status
- `payment_id` - FK to Payment (initial funding)
- `release_payment_id` - FK to Payment (release transaction)
- `admin_notes` - Admin comments
- `dispute_reason` - Reason if disputed
- `resolution_notes` - Resolution details
- `released_at` - Release timestamp
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `job` ↔ Job
- `employer` ↔ User
- `worker` ↔ User
- `payment` ↔ Payment
- `release_payment` ↔ Payment

---

#### **Review** (`app/models/review.py`)
User reviews and ratings

**Fields:**
- `id` (PK)
- `reviewer_id` - FK to User
- `reviewee_id` - FK to User
- `job_id` - FK to Job (context)
- `rating` - Float (1-5 stars)
- `comment` - Review text
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `reviewer` ↔ User
- `reviewee` ↔ User
- `job` ↔ Job

---

#### **Dispute** (`app/models/dispute.py`)
Conflict resolution mechanism

**Enums:**
- `DisputeStatus` - OPEN, UNDER_REVIEW, RESOLVED

**Fields:**
- `id` (PK)
- `job_id` - FK to Job
- `claimant_id` - FK to User (initiator)
- `defendant_id` - FK to User (accused)
- `reason` - Dispute description (Text)
- `status` - DisputeStatus enum
- `resolution` - Resolution details (Text)
- `resolved_by_admin_id` - FK to User (admin)
- `resolved_at` - Resolution timestamp
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `job` ↔ Job
- `claimant` ↔ User
- `defendant` ↔ User
- `resolved_by_admin` ↔ User

---

#### **Message** (`app/models/message.py`)
In-app messaging with real-time support

**Fields:**
- `id` (PK)
- `sender_id` - FK to User
- `receiver_id` - FK to User
- `content` - Message text
- `message_type` - MessageType enum (TEXT, FILE, etc.)
- `file_id` - FK to File (nullable)
- `is_read` - Read status boolean
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `sender` ↔ User
- `receiver` ↔ User
- `file` ↔ File

---

#### **Notification** (`app/models/notification.py`)
User notification tracking

**Fields:**
- `id` (PK)
- `user_id` - FK to User
- `message` - Notification text
- `read` - Read status boolean
- `created_at` - Timestamp

**Relationships:**
- `user` ↔ User

---

#### **KYCSubmission** (`app/models/kyc.py`)
Know Your Customer verification

**Fields:**
- `id` (PK)
- `user_id` - FK to User
- `document_type` - ID type (passport, national_id, etc.)
- `document_path` - File path to document
- `selfie_path` - File path to selfie
- `status` - Verification status (pending, approved, rejected)
- `notes` - Admin notes
- `verified_at` - Verification timestamp
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `user` ↔ User

---

#### **Badge** & **UserBadge** (`app/models/badge.py`)
Achievement system

**Badge Fields:**
- `id` (PK)
- `name` - Badge name (unique)
- `description` - Badge description
- `image_url` - Badge icon URL
- `criteria` - Award criteria (e.g., "rating>4.5")
- `created_at`, `updated_at` - Timestamps

**UserBadge Fields:**
- `id` (PK)
- `user_id` - FK to User
- `badge_id` - FK to Badge
- `awarded_at` - Award timestamp

**Relationships:**
- Badge → UserBadge (one-to-many)
- UserBadge → User

---

#### **File** (`app/models/file.py`)
File upload management

**Fields:**
- `id` (PK)
- `filename` - UUID-based filename
- `original_filename` - Original user filename
- `file_path` - Relative path to UPLOAD_DIR
- `file_type` - MIME type
- `file_size` - Size in bytes
- `category` - File category (avatar, job_attachment, kyc_document, etc.)
- `user_id` - FK to User (uploader)
- `reference_id` - ID of related entity (nullable)
- `reference_type` - Type of related entity (job, application, etc.)
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `user` ↔ User

---

#### **SubscriptionPlan** (`app/models/subscription.py`)
Subscription tiers for employers

**Fields:**
- `id` (PK)
- `name` - Plan name (unique, e.g., "Basic", "Pro")
- `price` - Monthly price in currency units
- `features` - JSON object with plan features
- `created_at`, `updated_at` - Timestamps

**Relationships:**
- `users` ↔ User (one-to-many)

**Features JSON Example:**
```json
{
  "applications_per_month": 50,
  "reduced_commission": 0.07,
  "support_priority": "standard",
  "featured_jobs": true
}
```

---

#### **Referral**, **Reward**, **ReferralSettings** (`app/models/referral.py`)
Referral program management

**Referral Enums:**
- `ReferralStatus` - PENDING, COMPLETED, REWARDED
- `RewardStatus` - PENDING, PAID

**Referral Fields:**
- `id` (PK)
- `referrer_id` - FK to User (person referring)
- `referred_id` - FK to User (person referred)
- `status` - ReferralStatus enum
- `created_at`, `updated_at` - Timestamps

**Reward Fields:**
- `id` (PK)
- `user_id` - FK to User (recipient)
- `referral_id` - FK to Referral
- `amount` - Reward amount
- `status` - RewardStatus enum
- `created_at`, `updated_at` - Timestamps

**ReferralSettings Fields:**
- `id` (PK)
- `user_role` - UserRole enum (ADMIN, EMPLOYER, WORKER)
- `reward_amount` - Reward per successful referral
- `is_active` - Enable/disable setting

---

#### **RecentWork** & **UserService** (`app/models/worker_profile.py`)
Worker portfolio

**RecentWork Fields:**
- `id` (PK)
- `user_id` - FK to User
- `description` - Project description (Text)
- `image_url` - Portfolio image URL

**UserService Fields:**
- `id` (PK)
- `user_id` - FK to User
- `service_name` - Service offered (e.g., "Web Development")

---

#### **Category** (`app/models/category.py`)
Job categories

**Fields:**
- `id` (PK)
- `name` - Category name (unique)

**Relationships:**
- `jobs` ↔ Job

---

#### **ServiceCategory** & **Service** (`app/models/service.py`)
Service offerings

**ServiceCategory Fields:**
- `id` (PK)
- `name` - Category name (unique)
- `description` - Category description

**Service Fields:**
- `id` (PK)
- `name` - Service name
- `category_id` - FK to ServiceCategory

---

#### **Transaction** (`app/models/transaction.py`)
Payment transaction tracking

**Enums:**
- `TransactionStatus` - PENDING, SUCCESS, FAILED

**Fields:**
- `id` (PK)
- `user_id` - FK to User
- `amount` - Transaction amount
- `status` - TransactionStatus enum
- `reference` - Unique reference (indexed)
- `created_at`, `updated_at` - Timestamps

---

#### **RecentActivity** (`app/models/recent_activity.py`)
User activity log

**Fields:**
- `id` (PK)
- `user_id` - FK to User (nullable)
- `activity_type` - Type of activity (application_submitted, job_posted, etc.)
- `description` - Activity description
- `activity_data` - JSON with additional context
- `timestamp` - Activity timestamp

---

#### **OTP** (`app/models/otp.py`)
One-time passwords for verification

**Fields:**
- `id` (PK) - UUID
- `otp_code` - 6-digit or alphanumeric code
- `user_id` - FK to User
- `purpose` - OTP purpose (email_verification, password_reset)
- `created_at` - Creation timestamp
- `expires_at` - Expiration timestamp

---

#### **Waitlist** (`app/models/waitlist.py`)
Pre-launch user registration

**Fields:**
- `id` (PK)
- `email` - User email (unique)
- `first_name`, `last_name` - Name
- `user_type` - Expected user type (employer/worker)
- `location` - User location
- `newsletter` - Newsletter subscription flag
- `created_at` - Signup timestamp

## 🔄 Workflows

### Job Creation & Application Workflow
```
1. Employer creates job → Job status = OPEN
2. Worker applies for job → JobApplication created
3. Escrow is funded if required → EscrowTransaction status = FUNDED
4. Employer reviews applications
5. Employer accepts application → ApplicationStatus = ACCEPTED
6. Job status → IN_PROGRESS
7. Worker completes work
8. Employer releases payment → Escrow status = RELEASED
9. Both users can leave reviews
10. Job status → COMPLETED
```

### Payment Processing Workflow
```
1. User initiates payment (wallet funding, application fee)
2. Redirect to Paystack for payment
3. Paystack processes transaction
4. Webhook received at POST /api/v1/payments/paystack-webhook
5. Payment status updated in database
6. User wallet/funds updated
7. Notification sent to user
8. Transaction recorded for history
```

### Paystack Webhook Security
All Paystack webhooks are verified using **HMAC-SHA512 signature verification** to prevent forged attacks.

**How it works:**
1. Paystack calculates: `signature = HMAC-SHA512(webhook_secret, raw_request_body).hexdigest()`
2. Paystack sends signature in `X-Paystack-Signature` header
3. Backend verifies by:
   - Getting raw request body
   - Computing expected signature using `PAYSTACK_WEBHOOK_SECRET`
   - Using constant-time comparison (`hmac.compare_digest()`) to prevent timing attacks
   - Returning 401 Unauthorized if signatures don't match

**Configuration:**
Set `PAYSTACK_WEBHOOK_SECRET` in your `.env` file:
```bash
PAYSTACK_WEBHOOK_SECRET=your_webhook_secret_from_paystack_dashboard
```

**Implementation:**
```python
from app.utils.paystack_webhook import PaystackWebhookVerifier

@app.post("/paystack-webhook")
async def handle_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Paystack-Signature")
    
    # This will raise HTTPException if signature is invalid
    PaystackWebhookVerifier.verify_and_raise(
        raw_body,
        signature,
        settings.PAYSTACK_WEBHOOK_SECRET,
        webhook_name="Webhook name"
    )
    
    # Process webhook payload...
```

**Webhook Endpoints:**
- `POST /api/v1/payments/callback` - Payment verification (charge.success)
- `POST /api/v1/withdrawals/paystack-webhook` - Transfer status (transfer.success, transfer.failed)

### Dispute Resolution Workflow
```
1. User creates dispute on a job
2. Dispute status = OPEN
3. Admin reviews dispute details
4. Admin requests evidence from both parties
5. Admin makes decision
6. Dispute resolved (Refund, Release, or Partial Release)
7. Escrow released accordingly
8. Notifications sent to both parties
```

## 🔗 WebSocket Endpoints

### Real-time Messaging
```
WS Connection: ws://localhost:8000/api/v1/ws/{user_id}

Message Format (JSON):
{
  "type": "message",
  "receiver_id": 2,
  "content": "Hello!"
}

Broadcast Event:
{
  "type": "message",
  "sender_id": 1,
  "content": "Hello!",
  "timestamp": "2024-12-25T10:30:00Z"
}
```

## 📊 Monitoring

### Prometheus Metrics
Metrics available at `http://localhost:8000/metrics`

Monitored metrics include:
- Request count and latency
- Database query performance
- Celery task execution time
- Payment processing metrics
- Error rates by endpoint

### Health Check
```bash
curl http://localhost:8000/health
# Response: {"status": "healthy"}
```

## 🚢 Production Deployment

### Using Docker Compose (Production)
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Using Systemd Service (Linux)
```bash
sudo cp install/jobconnect.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jobconnect
sudo systemctl start jobconnect
```

### Environment Considerations
- Set `DEBUG=False`
- Use strong `JWT_SECRET_KEY` (generate with `openssl rand -hex 32`)
- Enable SSL/TLS with valid certificates
- Configure `ALLOWED_ORIGINS` to only trusted domains
- Use managed PostgreSQL database (AWS RDS, DigitalOcean, etc.)
- Set up log aggregation (ELK, Datadog, etc.)
- Configure backup strategies for database
- Use environment-specific `.env` files

## 📝 API Changelog

See [API_CHANGES.md](API_CHANGES.md) for detailed endpoint changes and updates.

See [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for comprehensive system architecture documentation.

## 🐛 Known Issues & Limitations

- File uploads currently stored locally; consider S3 integration for production
- WebSocket connections require manual reconnection on network loss
- Rate limiting reset on server restart (use Redis for production)
- Celery tasks require Redis connection; will fail if Redis unavailable

## 🤝 Contributing

1. Create a feature branch (`git checkout -b feature/AmazingFeature`)
2. Commit your changes (`git commit -m 'Add AmazingFeature'`)
3. Push to the branch (`git push origin feature/AmazingFeature`)
4. Open a Pull Request

## 📄 License

MIT License - see LICENSE file for details

## 📚 Complete File Reference Summary

### Models (`app/models/`) - 27 Files
**Core Models (User & Jobs):**
- `user.py` - User accounts with 3 roles, reputation, wallet
- `job.py` - Job postings with status lifecycle and escrow
- `job_application.py` - Worker applications with fee tracking

**Financial & Transactions:**
- `payment.py` - Payment records for all transaction types
- `escrow_transaction.py` - Safe fund holding with 10% commission
- `transaction.py` - Low-level transaction tracking

**User Interactions:**
- `review.py` - Ratings and feedback (1-5 stars)
- `message.py` - In-app messaging with file support
- `notification.py` - User notification tracking
- `recent_activity.py` - Activity log with JSON data

**Verification & Compliance:**
- `kyc.py` - Know Your Customer documents and status
- `otp.py` - One-time passwords for verification
- `token_blacklist.py` - Invalidated JWT tokens

**Gamification & Rewards:**
- `badge.py` - Achievement badges and user awards
- `referral.py` - Referral codes, rewards, settings
- `reward.py` (in referral.py) - Reward tracking

**System Management:**
- `subscription.py` - Subscription plans with JSON features
- `category.py` - Job categories
- `service.py` - Services and service categories
- `file.py` - File uploads with category and reference tracking
- `worker_profile.py` - Recent work portfolio and services
- `dispute.py` - Dispute resolution with admin arbitration
- `countdown.py` - Launch countdown
- `newsletter.py` - Email newsletter campaigns
- `waitlist.py` - Pre-launch user registration
- `enums.py` - Shared enumerations
- `user_role.py` - User role definitions

---

### Routers (`app/routers/`) - 20 Files
**Authentication & Users:**
- `auth.py` - Register, login, password reset, OTP verification
- `users.py` - Profile, avatar, wallet, role switching
- `worker.py` - Worker profile, portfolio, services

**Core Marketplace:**
- `jobs.py` - Create, search, filter, update jobs
- `categories.py` - Job category listing
- `payments.py` - Payment initialization, webhook, wallet operations
- `files.py` - Upload, download, delete files

**Interactions & Communication:**
- `messages.py` - HTTP messages + WebSocket real-time messaging
- `notification.py` - In-app notifications
- `reviews.py` - Create reviews, statistics
- `badges.py` - Badge creation, awarding

**Transactions & Safety:**
- `dispute.py` - Create disputes, resolution
- `subscription.py` - Plans, subscriptions, status
- `kyc.py` - KYC submission, verification

**Features:**
- `referral.py` - Referral codes, tracking
- `recent_activity.py` - Activity feed (user and admin)
- `waitlist.py` - Waitlist, countdown
- `dashboard.py` - User dashboard data
- `admin.py` - Comprehensive admin operations (440+ lines)
- `revenue.py` - Revenue reporting

---

### Services (`app/services/`) - 23 Files
**Core Services:**
- `auth_service.py` - Authentication, JWT, password management
- `user_service.py` - Profile, reputation, wallet operations
- `job_service.py` - Job CRUD, search, lifecycle
- `payment_service.py` - Paystack integration, wallet, commission
- `transaction_service.py` - Transaction tracking

**Transaction Services:**
- `review_service.py` - Rating and feedback logic
- `dispute_service.py` - Dispute creation, resolution
- `escrow_service.py` (in payment_service.py) - Escrow operations

**Verification & Admin:**
- `kyc_service.py` - Document verification, external API
- `admin_service.py` - Dashboard, user management, moderation
- `worker_service.py` - Worker-specific operations

**Communication & Notifications:**
- `message_service.py` - Messaging, WebSocket handling
- `notification_service.py` - Notification creation, management
- `system_message_service.py` - System-wide messaging

**Content & Features:**
- `badge_service.py` - Badge awards, criteria checking
- `file_service.py` - File upload, validation, storage
- `subscription_service.py` - Subscription management
- `referral_service.py` - Referral codes, rewards
- `category_service.py` - Category management
- `countdown_service.py` - Launch countdown
- `newsletter_service.py` - Newsletter management
- `otp_service.py` - OTP generation, validation
- `recent_activity_service.py` - Activity logging
- `waitlist_service.py` - Waitlist management

---

### Schemas (`app/schemas/`) - 27 Files
**Authentication & Authorization:**
- `auth.py` - Login, register, OTP, password reset requests/responses
- `user.py` - User CRUD, profile, role switching DTOs

**Core Marketplace:**
- `job.py` - Job CRUD, filters, responses
- `job_application.py` - Application requests, status updates
- `job_with_applications.py` - Job with nested applications
- `job_with_application_count.py` - Job with count

**Financial:**
- `payment.py` - Payment requests, responses, status
- `billing.py` - Billing-related DTOs
- `transaction.py` - Transaction creation, response
- `escrow.py` - Escrow details, status

**User Interactions:**
- `review.py` - Review creation, rating response
- `message.py` - Message creation, conversation response
- `notification.py` - Notification creation, response

**Verification:**
- `kyc.py` - KYC submission, verification, status
- `otp.py` - OTP schemas

**Content & Features:**
- `badge.py` - Badge creation, user badge response
- `category.py` - Category response DTOs
- `service.py` - Service creation, response
- `subscription.py` - Plan creation, update, response
- `countdown.py` - Countdown response
- `newsletter.py` - Newsletter creation, update, response
- `waitlist.py` - Waitlist entry, response
- `worker_profile.py` - Worker profile DTOs
- `dispute.py` - Dispute creation, update, response
- `recent_activity.py` - Activity log response
- `referral.py` - Referral code, settings, response
- `admin.py` - Dashboard stats, user lists, dispute lists

---

### Tasks (Background Jobs) (`app/tasks/`) - 4 Files
- `notifications.py` - Email/SMS notifications via Mailgun/Twilio
- `cleanup.py` - Database cleanup, token expiration
- `payments.py` - Payment processing, escrow release
- `newsletter.py` - Newsletter distribution campaigns
- `waitlist.py` - Launch notification sending

---

### Utilities & Helpers (`app/utils/`, `app/middlewares/`, `app/dependencies/`)
**Security & Auth:**
- `security.py` - JWT creation/validation, password hashing
- `validators.py` - Input validation helpers

**External Services:**
- `email.py` - SMTP email sending
- `sms.py` - Twilio SMS integration
- `file_handler.py` - File storage operations

**Middleware & Dependencies:**
- `error_handler.py` - Global exception handling
- `rate_limiter.py` - Request rate limiting
- `rate_limiter.py` (dependencies) - Rate limiter logic
- `application_fee.py` - Fee calculation logic
- `subscription.py` - Subscription validation
- `worker.py` - Worker role checking

---

### Database & Configuration
- `database.py` - Async SQLAlchemy setup, read/write routing
- `config.py` - Environment settings from .env
- `main.py` - FastAPI app initialization, middleware setup
- `websocket_manager.py` - WebSocket connection pooling
- `db/base_class.py` - SQLAlchemy declarative base

---

### Alembic Migrations (`alembic/`)
- `env.py` - Migration environment configuration
- `script.py.mako` - Migration template
- `versions/` - Migration scripts (database schema versioning)

---

## 📧 Support

For issues, questions, or suggestions:
- Create an issue on GitHub
- Contact: support@jobconnect.com
- Documentation: https://docs.jobconnect.com
# jobconnect-backend
