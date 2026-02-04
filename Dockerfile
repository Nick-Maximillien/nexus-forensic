FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /apps

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --default-timeout=1000 --no-cache-dir

COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "medgate.wsgi:application", "--bind", "0.0.0.0:8000"]