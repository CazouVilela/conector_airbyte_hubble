FROM airbyte/python-connector-base:4.1.0

WORKDIR /airbyte/integration_code

# Copy source files
COPY source_hubble ./source_hubble
COPY main.py ./
COPY setup.py ./
COPY README.md ./

# Install dependencies
RUN pip install --no-cache-dir .

# Airbyte configuration
ENV AIRBYTE_ENTRYPOINT="python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

# Labels
LABEL io.airbyte.version=1.0.0
LABEL io.airbyte.name=airbyte/source-hubble
LABEL io.airbyte.protocol-version=0.2.0
