FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including libpff/pypff build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    autoconf \
    automake \
    autopoint \
    libtool \
    pkg-config \
    git \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Build and install pypff (PST file parser) from source
# Use PYTHON env var to point configure at the base image's Python 3.11
RUN git clone https://github.com/libyal/libpff.git /tmp/libpff \
    && cd /tmp/libpff \
    && ./synclibs.sh \
    && ./autogen.sh \
    && PYTHON=python3 ./configure --enable-python \
    && make -j$(nproc) \
    && make install \
    && ldconfig \
    && cd /tmp/libpff && python3 setup.py install \
    && rm -rf /tmp/libpff

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-keep-alive", "300"]
