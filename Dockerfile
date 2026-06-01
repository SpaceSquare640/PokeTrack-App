# PokéTrack web app — container image.
#   docker build -t poketrack .
#   docker run -p 5000:5000 poketrack   ->   http://localhost:5000/
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bind to all interfaces inside the container (run_web.py honours these envs).
ENV PYTHONUNBUFFERED=1 \
    POKETRACK_WEB_HOST=0.0.0.0 \
    POKETRACK_WEB_PORT=5000

EXPOSE 5000
CMD ["python", "run_web.py"]
