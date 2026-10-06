ARG PYTHON_IMAGE=python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
FROM ${PYTHON_IMAGE}

ARG A2FLOW_UID=1000
ARG A2FLOW_GID=1000
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONPATH=/opt/a2flow/packages/contracts/src:/opt/a2flow/packages/asset-store/src:/opt/a2flow/services/skill-registry/src:/opt/a2flow/services/capability-registry/src:/opt/a2flow/services/a2ui-composer/src:/opt/a2flow/services/b-side-api/src:/opt/a2flow/services/scheduler-mq/src:/opt/a2flow/services/agent-workflow-runtime/src:/opt/a2flow/examples/activity-planning

WORKDIR /opt/a2flow

COPY experiments/runtime-phase1/requirements.lock /tmp/runtime-requirements.lock
COPY deploy/mvp/model-requirements.lock /tmp/model-requirements.lock
COPY deploy/mvp/listener-requirements.lock /tmp/listener-requirements.lock
COPY services/agent-workflow-runtime/requirements-http.txt /tmp/runtime-http.txt
COPY services/b-side-api/requirements-http.txt /tmp/bside-http.txt
RUN python -m pip install --no-cache-dir -r /tmp/runtime-requirements.lock \
    && python -m pip install --no-cache-dir -r /tmp/model-requirements.lock \
    && python -m pip install --no-cache-dir --no-deps --require-hashes \
        -r /tmp/runtime-http.txt \
    && python -m pip install --no-cache-dir --no-deps --require-hashes \
        -r /tmp/bside-http.txt \
    && python -m pip install --no-cache-dir -r /tmp/listener-requirements.lock \
    && python -m pip install --no-cache-dir \
        -c /tmp/runtime-requirements.lock \
        annotated-doc==0.0.5 anyio==4.15.1 pydantic==2.13.5 \
        psycopg==3.3.5 psycopg-binary==3.3.5 typing_extensions==4.16.0 jsonschema==4.26.0 \
    && rm -f /tmp/*.lock /tmp/*.txt

COPY packages/contracts packages/contracts
COPY packages/asset-store packages/asset-store
COPY packages/rpc-contracts packages/rpc-contracts
RUN python -m pip install --no-cache-dir /opt/a2flow/packages/rpc-contracts
COPY services/skill-registry services/skill-registry
COPY services/capability-registry services/capability-registry
COPY services/a2ui-composer services/a2ui-composer
COPY services/b-side-api services/b-side-api
COPY services/scheduler-mq services/scheduler-mq
COPY services/agent-workflow-runtime services/agent-workflow-runtime
COPY examples/activity-planning examples/activity-planning
COPY experiments/runtime-phase1 experiments/runtime-phase1
COPY deploy/__init__.py deploy/__init__.py
COPY deploy/assets.py deploy/assets.py
COPY deploy/mvp deploy/mvp
COPY deploy/attended deploy/attended

RUN groupadd --system --gid ${A2FLOW_GID} a2flow \
    && useradd --system --uid ${A2FLOW_UID} --gid ${A2FLOW_GID} \
        --home-dir /nonexistent --shell /usr/sbin/nologin a2flow

USER ${A2FLOW_UID}:${A2FLOW_GID}
ENTRYPOINT ["python", "-m", "deploy.attended.launcher"]
CMD ["--help"]
