# Reuse the already installed SDK environment; source is from the reviewed SHA.
ARG SDK_IMAGE=a2flow-attended:af13
FROM ${SDK_IMAGE}
USER root
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} jsonschema==4.26.0
COPY packages /opt/a2flow/packages
COPY services /opt/a2flow/services
COPY examples/activity-planning /opt/a2flow/examples/activity-planning
COPY deploy /opt/a2flow/deploy
USER 1000:1000
ENTRYPOINT ["python", "-m", "deploy.realchat.launcher"]
