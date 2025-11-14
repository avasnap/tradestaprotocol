# TradeSta Verification Suite - Docker Image
#
# This container provides a reproducible environment for verifying
# the TradeSta protocol using only public blockchain data sources.

FROM python:3.11-slim

# Set working directory
WORKDIR /verification

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy verification scripts
COPY scripts/ scripts/

# Create directories for results and cache
RUN mkdir -p results cache

# Default command runs basic verification (sample of 3 markets)
# For full verification on all markets, run:
#   docker run tradesta-verify python3 scripts/verify_all_phase2.py --all
CMD ["python3", "scripts/verify_all.py"]
