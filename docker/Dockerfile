# CircuitWeaver Docker Image
# Includes KiCad for full compilation and ERC support

FROM python:3.11-slim-bookworm

LABEL maintainer="CircuitWeaver Contributors"
LABEL description="MCP server for generating KiCad schematics from Circuit JSON"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # KiCad and dependencies
    kicad \
    kicad-libraries \
    # Build tools
    git \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash circuitweaver

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

# Install CircuitWeaver
RUN pip install --no-cache-dir -e .

# Switch to non-root user
USER circuitweaver

# Create workspace directory
RUN mkdir -p /home/circuitweaver/workspace

WORKDIR /home/circuitweaver/workspace

# Default command: start MCP server in stdio mode
ENTRYPOINT ["circuitweaver"]
CMD ["serve"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD circuitweaver info || exit 1

# Expose port for HTTP mode
EXPOSE 3000
