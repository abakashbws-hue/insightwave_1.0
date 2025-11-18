FROM python:3.11-slim

# 1. Install Nginx
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install ADK (and other dependencies)
COPY insightwave/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV GOOGLE_GENAI_USE_VERTEXAI=1
ENV GOOGLE_CLOUD_PROJECT='insightwave-dev'
ENV GOOGLE_CLOUD_LOCATION='us-central1'
ENV INSIGHTWAVE_ARTIFACT_BUCKET='insightwave-report-artifacts'
ENV GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY='true'

# 3. Copy Agent Code
# adk web looks for the agent in the current directory
COPY insightwave/ ./insightwave/

# 4. Copy Configuration
COPY nginx.conf /etc/nginx/sites-available/default
COPY start.sh .
RUN chmod +x start.sh

# 5. Copy Angular Build
COPY ui_build/ ./ui_build/

# 6. Run
CMD ["./start.sh"]