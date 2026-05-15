@echo off
echo "================================================="
echo "JobConnect Windows Setup"
echo "================================================="
echo.

echo "This script will guide you through setting up the JobConnect application on Windows."
echo "Some steps require manual installation."
echo.

echo "Step 1: Install Dependencies"
echo "--------------------------------"
echo "Please install the following software manually:"
echo "- Python 3: https://www.python.org/downloads/"
echo "- PostgreSQL 14: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads"
echo "- Redis: https://redis.io/docs/getting-started/installation/install-redis-on-windows/"
echo.
pause

echo "Step 2: Create PostgreSQL Database"
echo "--------------------------------"
echo "Please create a new PostgreSQL database named 'jobconnect'."
echo "You will also need to create a user and grant it ownership of the database."
echo "Note down the username and password."
echo.
set /p DB_USER="Enter the database username: "
set /p DB_PASSWORD="Enter the database password: "
echo.

echo "Step 3: Configure .env file"
echo "--------------------------------"
if exist ".env.example" (
    copy .env.example .env
    echo "DATABASE_URL=postgresql+asyncpg://%DB_USER%:%DB_PASSWORD%@localhost:5432/jobconnect" > .env
    echo "REDIS_URL=redis://localhost:6379/0" >> .env
    echo ".env file configured."
) else (
    echo ".env.example not found!"
    exit /b 1
)
echo.

echo "Step 4: Install Python Requirements"
echo "--------------------------------"
echo "Creating virtual environment..."
python -m venv .venv
echo "Activating virtual environment and installing requirements..."
call .venv\Scripts\activate.bat
pip install -r requirements.txt
echo.

echo "Step 5: Initialize Database"
echo "--------------------------------"
echo "Running database migrations..."
alembic upgrade head
echo.

echo "Step 6: Run the Application"
echo "--------------------------------"
echo "You can now run the application using the following command:"
echo "uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo.

echo "Setup complete."
pause
