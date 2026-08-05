# Build the thesis DOCX/PDF in a container with LibreOffice as the engine.
#
#   docker build -t vkr-builder .
#   docker run --rm -v "$PWD/out:/work/example" vkr-builder build --pdf
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends -o Dpkg::Use-Pty=0 \
        libreoffice-writer \
        libreoffice-math \
        fonts-liberation \
        python3-uno \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

ENV VKR_PROG="docker run --rm vkr-builder"

ENTRYPOINT ["python", "main.py"]
CMD ["build"]
