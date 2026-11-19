# Runs the end-to-end tests: Python, Selenium, and a headless Chromium with its driver.
# (Chromium rather than Google Chrome because Google publishes no Linux build for
# Apple-silicon containers. It is the same browser engine.)
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /e2e

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
