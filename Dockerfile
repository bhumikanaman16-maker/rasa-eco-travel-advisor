# EcoTravel Advisor – Dockerfile
# MSc Assignment: Sustainable Tourism Planning Chatbot
#
# This Dockerfile builds the Rasa action server.
# The Rasa server is started separately (see docker-compose.yml).

FROM rasa/rasa-sdk:3.6.2

WORKDIR /app

# Copy action server files
COPY actions/ ./actions/
COPY data/external/ ./data/external/

# Install additional Python dependencies
COPY requirements.txt .
USER root
RUN pip install --no-cache-dir python-dotenv requests "SQLAlchemy<2.0"
USER 1001

# Expose action server port
EXPOSE 5055

# Environment variables must be provided at runtime via --env-file
# Do NOT hard-code any API keys in this file.

CMD ["start", "--actions", "actions"]
