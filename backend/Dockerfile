FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies.
#
# The font packages mirror Dockerfile.prod on purpose. Without them Pillow's
# truetype() calls all fail and silently fall back to a tiny fixed-size bitmap
# font, so generated posters look broken in dev while being perfect in prod —
# a "dev red / prod green" gap that costs real debugging time.
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    fonts-noto-cjk \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
