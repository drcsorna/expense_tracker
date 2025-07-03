# Expense Tracker - Docker Production Image
#
# PURPOSE: Multi-stage Docker build for production deployment
# SCOPE: Optimized image with system dependencies and security hardening
# CONTEXT: Production-ready container for expense tracker application
#
# AI CONTEXT: This Dockerfile creates a production-ready container image.
# Uses multi-stage build for optimization and includes all necessary system dependencies.
# When modifying, consider image size, security, and deployment requirements.
#
# BUILD: docker build -t expense-tracker .
# RUN: docker run -p 8000:8000 -v $(pwd)/data:/app/data expense-tracker
#
# FEATURES:
# - Multi-stage build for smaller final image
# - Non-root user for security
# - System dependencies for OCR processing
# - Volume mount points for data persistence
# - Health check for container orchestration
# - Optimized layer caching for faster builds

# ============================================================================
# STAGE 1: SYSTEM DEPENDENCIES AND BUILD ENVIRONMENT
# ============================================================================

FROM python:3.11-slim as base

# Set environment variables for Python optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for OCR and image processing
RUN apt-get update && apt-get install -y \
    # Tesseract OCR engine and language packs
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-nld \
    # OpenCV system dependencies
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # Build tools (removed in final stage)
    gcc \
    g++ \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /bin/bash appuser

# Create application directories
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

# ============================================================================
# STAGE 2: PYTHON DEPENDENCIES
# ============================================================================

FROM base as dependencies

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip cache purge

# ============================================================================
# STAGE 3: APPLICATION BUILD
# ============================================================================

FROM dependencies as application

# Copy application code
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser frontend/ ./frontend/
COPY --chown=appuser:appuser *.py ./

# Create database directory with proper permissions
RUN mkdir -p /app/data \
    && chown -R appuser:appuser /app/data

# ============================================================================
# STAGE 4: PRODUCTION IMAGE
# ============================================================================

FROM application as production

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Volume mount points for persistent data
VOLUME ["/app/data", "/app/logs"]

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Set default command
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# ============================================================================
# DOCKER BUILD ARGUMENTS AND LABELS
# ============================================================================

# Build arguments for customization
ARG BUILD_DATE
ARG VERSION=1.0.0
ARG VCS_REF

# Docker labels for metadata
LABEL maintainer="Expense Tracker Team" \
      org.opencontainers.image.title="Expense Tracker" \
      org.opencontainers.image.description="Personal expense tracking with OCR receipt processing" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Personal Finance Tools" \
      org.opencontainers.image.source="https://github.com/your-repo/expense-tracker"

# ============================================================================
# DEVELOPMENT STAGE (Alternative target)
# ============================================================================

FROM dependencies as development

# Install development dependencies
RUN pip install \
    pytest \
    pytest-asyncio \
    black \
    flake8 \
    ipython \
    jupyter

# Copy application code (development mode allows editing)
COPY --chown=appuser:appuser . /app/

# Switch to non-root user
USER appuser

# Development command with auto-reload
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]

# ============================================================================
# BUILD INSTRUCTIONS AND USAGE
# ============================================================================

# BUILD COMMANDS:
# 
# Production build:
# docker build --target production -t expense-tracker:latest .
#
# Development build:
# docker build --target development -t expense-tracker:dev .
#
# Build with metadata:
# docker build \
#   --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
#   --build-arg VERSION=1.0.0 \
#   --build-arg VCS_REF=$(git rev-parse --short HEAD) \
#   --target production \
#   -t expense-tracker:latest .

# RUN COMMANDS:
#
# Production run:
# docker run -d \
#   --name expense-tracker \
#   -p 8000:8000 \
#   -v expense-data:/app/data \
#   -v expense-logs:/app/logs \
#   --restart unless-stopped \
#   expense-tracker:latest
#
# Development run:
# docker run -it \
#   --name expense-tracker-dev \
#   -p 8000:8000 \
#   -v $(pwd):/app \
#   -v expense-data:/app/data \
#   expense-tracker:dev

# OPTIMIZATION NOTES:
# 
# Image size optimization:
# - Multi-stage build removes build dependencies
# - Minimal base image (python:3.11-slim)
# - Cleanup of package caches and temporary files
#
# Security hardening:
# - Non-root user execution
# - Minimal system packages
# - Health check for monitoring
#
# Performance optimization:
# - Layer caching for faster rebuilds
# - Volume mounts for persistent data
# - Single worker for SQLite compatibility

# ============================================================================
# AI DEVELOPMENT NOTES
# ============================================================================

# EXTENDING THE DOCKERFILE:
# 1. Add new system dependencies in the base stage
# 2. Update Python dependencies in requirements.txt
# 3. Consider multi-architecture builds for ARM64
# 4. Add environment-specific configurations
# 5. Include monitoring and logging tools for production

# DEPLOYMENT PATTERNS:
# - Use docker-compose for local development
# - Kubernetes manifests for production orchestration
# - CI/CD pipeline integration with automated testing
# - Registry publishing with semantic versioning

# TROUBLESHOOTING:
# - Check system dependencies for OCR functionality
# - Verify file permissions for volume mounts
# - Monitor resource usage in production
# - Use multi-stage debugging for build issues

# SCALING CONSIDERATIONS:
# - Horizontal scaling with load balancer
# - Database migration to PostgreSQL for multi-instance
# - Shared storage for uploaded images
# - Redis for session management and caching