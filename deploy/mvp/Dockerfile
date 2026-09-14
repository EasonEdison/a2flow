ARG PYTHON_IMAGE=python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
FROM ${PYTHON_IMAGE}

ARG A2FLOW_UID=10001
ARG A2FLOW_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/a2flow/packages/contracts/src:/opt/a2flow/packages/asset-store/src:/opt/a2flow/services/skill-registry/src:/opt/a2flow/services/capability-registry/src:/opt/a2flow/services/agent-workflow-runtime/src:/opt/a2flow/examples/activity-planning

WORKDIR /opt/a2flow

COPY experiments/runtime-phase1/requirements.lock /tmp/runtime-requirements.lock
COPY services/agent-workflow-runtime/requirements-http.txt /tmp/http-requirements.txt
COPY deploy/mvp/listener-requirements.lock /tmp/listener-requirements.lock
COPY deploy/mvp/model-requirements.lock /tmp/model-requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/runtime-requirements.lock \
    && python -m pip install --no-cache-dir -r /tmp/model-requirements.lock \
    && python -m pip install --no-cache-dir --no-deps --require-hashes -r /tmp/http-requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/listener-requirements.lock \
    && rm -f /tmp/*-requirements.lock /tmp/http-requirements.txt

COPY packages/contracts packages/contracts
COPY packages/asset-store packages/asset-store
COPY services/skill-registry services/skill-registry
COPY services/capability-registry services/capability-registry
COPY services/agent-workflow-runtime services/agent-workflow-runtime
COPY examples/activity-planning examples/activity-planning
COPY deploy deploy

RUN groupadd --system --gid ${A2FLOW_GID} a2flow \
    && useradd --system --uid ${A2FLOW_UID} --gid ${A2FLOW_GID} \
        --home-dir /nonexistent --shell /usr/sbin/nologin a2flow \
    && install -d -o a2flow -g a2flow -m 0700 /var/lib/a2flow

USER 10001:10001
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "deploy.mvp.app:app", "--host", "0.0.0.0", "--port", "8765", "--no-access-log"]
