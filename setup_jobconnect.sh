#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
DB_USER=$(whoami)
DB_PASSWORD="3def760ce0e157343d96949c"
DB_NAME="jobconnect"
ADMIN_EMAIL="admin@jobconnect.ng"
ADMIN_PASSWORD="Admin@123!"

# --- Helper Functions ---
log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
    exit 1
}

# --- Main Setup Functions ---

# 1. Install system packages
install_packages() {
    log_info "Updating package list and installing dependencies..."
    if [ -f /etc/debian_version ]; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv redis-server postgresql openssl
    else
        log_error "This script is intended for Debian-based systems only."
    fi
}

# 2. Set up PostgreSQL database
setup_database() {
    log_info "Setting up PostgreSQL database..."
    # Check if user and database already exist
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
        log_info "PostgreSQL user '${DB_USER}' already exists. Updating password."
        sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
    else
        log_info "Creating PostgreSQL user '${DB_USER}'."
        sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
    fi

    log_info "Terminating any existing connections to the database..."
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}';"

    log_info "Dropping existing database if it exists..."
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};"
    
    log_info "Creating new database..."
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
    log_info "Database '${DB_NAME}' created and assigned to '${DB_USER}'."

    log_info "Setting current user as owner of the public schema..."
    sudo -u postgres psql -d ${DB_NAME} -c "ALTER SCHEMA public OWNER TO ${DB_USER};"
}

# 3. Configure the .env file
configure_env() {
    log_info "Configuring .env file..."
    if [ ! -f .env ]; then
        cp .env.example .env
        log_info ".env file created from .env.example."
    else
        log_info ".env file already exists. Updating settings."
    fi

    # Update database URL
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}|" .env
    sed -i "s|^READ_REPLICA_DATABASE_URL=.*|READ_REPLICA_DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}|" .env
    
    # Update Redis URL
    sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|" .env

    # Configure SSL
    sed -i "s|^ENABLE_SSL=.*|ENABLE_SSL=True|" .env
    sed -i "s|^SSL_CERT_PATH=.*|SSL_CERT_PATH=$(pwd)/ssl/cert.pem|" .env
    sed -i "s|^SSL_KEY_PATH=.*|SSL_KEY_PATH=$(pwd)/ssl/key.pem|" .env

    # Add admin credentials if they don't exist
    grep -qxF "DEFAULT_ADMIN_EMAIL=${ADMIN_EMAIL}" .env || echo "DEFAULT_ADMIN_EMAIL=${ADMIN_EMAIL}" >> .env
    grep -qxF "DEFAULT_ADMIN_PASSWORD=${ADMIN_PASSWORD}" .env || echo "DEFAULT_ADMIN_PASSWORD=${ADMIN_PASSWORD}" >> .env

    log_info ".env file configured successfully."
}

# 4. Set up Python environment and install dependencies
setup_python_env() {
    log_info "Setting up Python virtual environment..."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
        log_info "Virtual environment created."
    else
        log_info "Virtual environment already exists."
    fi

    log_info "Installing Python requirements..."
    source .venv/bin/activate
    pip install -r requirements.txt
    deactivate
    log_info "Python requirements installed."
}

# 5. Initialize the database with schema and data
initialize_database() {
    log_info "Initializing database..."
    source .venv/bin/activate
    
    log_info "Removing old migrations..."
    mkdir -p alembic/versions
    rm -f alembic/versions/*.py
    
    log_info "Generating new initial migration..."
    alembic revision --autogenerate -m "Initial migration"

    log_info "Running database migrations..."
    alembic upgrade head
    
    deactivate
    log_info "Database initialized."
}

# 6. Generate SSL certificate
generate_ssl_cert() {
    log_info "Generating self-signed SSL certificate..."
    mkdir -p ssl
    openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem \
    -sha256 -days 365 -nodes -subj "/C=XX/ST=State/L=City/O=Organization/OU=OrgUnit/CN=localhost"
    log_info "SSL certificate created in ssl/ directory."
}

# 7. Set up and enable the systemd service
setup_systemd_service() {
    log_info "Setting up systemd service..."
    SERVICE_FILE="/etc/systemd/system/jobconnect.service"
    
    sudo bash -c "cat > ${SERVICE_FILE}" <<EOF
[Unit]
Description=JobConnect Application Service
After=network.target postgresql.service redis.service

[Service]
User=$(whoami)
Group=$(id -gn $(whoami))
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python $(pwd)/run_ssl.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable jobconnect.service
    sudo systemctl start jobconnect.service
    
    log_info "JobConnect systemd service created, enabled, and started."
    log_info "You can check the status with: sudo systemctl status jobconnect.service"
}

# --- Main Execution ---
main() {
    log_info "Starting JobConnect application setup..."
    
    install_packages
    setup_database
    configure_env
    setup_python_env
    initialize_database
    generate_ssl_cert
    setup_systemd_service
    
    log_info "-----------------------------------------------------"
    log_info "JobConnect setup is complete!"
    log_info "The application is now running as a systemd service with SSL."
    log_info "You can access it at https://localhost:8000"
    log_info "-----------------------------------------------------"
}

main
