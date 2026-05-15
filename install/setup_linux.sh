#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to detect the Linux distribution and install packages
install_packages() {
    if [ -f /etc/debian_version ]; then
        echo "Debian-based system detected. Using apt."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip redis-server postgresql-14
    elif [ -f /etc/redhat-release ]; then
        echo "Red Hat-based system detected. Using dnf."
        sudo dnf check-update
        sudo dnf install -y python3 python3-pip redis postgresql-server
        sudo postgresql-setup --initdb
        sudo systemctl enable --now postgresql
    else
        echo "Unsupported Linux distribution."
        exit 1
    fi
}

# Function to generate random credentials
generate_credentials() {
    DB_USER="jobconnect_user"
    DB_PASSWORD=$(openssl rand -hex 12)
}

# Function to set up PostgreSQL
setup_database() {
    echo "Setting up PostgreSQL..."
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
    sudo -u postgres psql -c "CREATE DATABASE jobconnect OWNER ${DB_USER};"
    echo "Database 'jobconnect' and user '${DB_USER}' created."
}

# Function to configure the .env file
configure_env() {
    echo "Configuring .env file..."
    if [ -f .env.example ]; then
        cp .env.example .env
        sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/jobconnect|" .env
        sed -i "s|REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|" .env
        echo ".env file configured."
    else
        echo ".env.example not found!"
        exit 1
    fi
}

# Function to install Python dependencies
install_requirements() {
    echo "Installing Python requirements..."
    pip3 install -r requirements.txt
}

# Function to set up systemd service
setup_systemd() {
    echo "Setting up systemd service..."
    sudo bash -c 'cat > /etc/systemd/system/jobconnect.service' <<EOF
[Unit]
Description=JobConnect Application
After=network.target postgresql.service redis.service

[Service]
User=${USER}
Group=$(id -gn $USER)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now jobconnect.service
    echo "JobConnect service created and started."
}

# Main script execution
install_packages
generate_credentials
setup_database
configure_env
python3 -m venv .venv
source .venv/bin/activate
install_requirements
# alembic upgrade head # This should be run after the virtualenv is created and packages are installed
setup_systemd

echo "JobConnect setup is complete."
echo "Database User: ${DB_USER}"
echo "Database Password: ${DB_PASSWORD}"
