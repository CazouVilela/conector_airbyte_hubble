FROM airbyte/python-connector-base:1.1.0

WORKDIR /airbyte/integration_code

COPY source_hubble ./source_hubble
COPY main.py ./
COPY setup.py ./

RUN pip install .

ENV AIRBYTE_ENTRYPOINT="python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-hubble
