FROM python:3.12-slim

# Set environment variables
ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    # Fix for the common "Keyring" crash in Docker
    PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring

ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy configuration
COPY pyproject.toml poetry.lock* ./

# Principal Move: Show us the error!
# We run 'poetry lock' inside just in case your local lock is out of sync
RUN poetry install --no-root --no-ansi


COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]