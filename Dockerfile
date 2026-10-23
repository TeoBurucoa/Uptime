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

# Create directories for history and failed emails
RUN mkdir -p data email_fail

EXPOSE 8080

# Command to run the script
CMD ["/bin/sh", "-c", "python python_files/main.py --domains \"$DOMAINS_FILE\" --from-email \"$FROM_EMAIL\" --password \"$EMAIL_PASSWORD\" --host 0.0.0.0 --port 8080 --no-browser"]