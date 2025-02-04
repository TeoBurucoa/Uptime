# Use official Python runtime as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install ping utility
RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY python_files/requirements.txt python_files/.

# Install dependencies
RUN pip install --no-cache-dir -r python_files/requirements.txt

# Copy all project files
COPY . .

# Create directories for alerts and archive
RUN mkdir -p alerts archive email_fail

# Command to run the script
CMD ["/bin/sh", "-c", "python python_files/main.py --domains \"$DOMAINS_FILE\" --from-email \"$FROM_EMAIL\" --password \"$EMAIL_PASSWORD\""]