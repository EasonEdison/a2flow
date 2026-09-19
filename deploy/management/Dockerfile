ARG PYTHON_IMAGE=python:3.11.14-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
FROM ${PYTHON_IMAGE}

ARG A2FLOW_UID=1000
ARG A2FLOW_GID=1000
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONPATH=/opt/a2flow/packages/contracts/src:/opt/a2flow/packages/asset-store/src:/opt/a2flow/services/skill-registry/src:/opt/a2flow/services/capability-registry/src:/opt/a2flow/services/a2ui-composer/src:/opt/a2flow/services/workflow-composer/src:/opt/a2flow/services/management-api/src:/opt/a2flow/examples/activity-planning

WORKDIR /opt/a2flow

COPY experiments/runtime-phase1/requirements.lock /tmp/runtime-constraints.lock
COPY services/management-api/requirements-http.txt /tmp/management-http.txt
COPY deploy/mvp/listener-requirements.lock /tmp/listener-requirements.lock
RUN python -m pip install --no-cache-dir \
        -c /tmp/runtime-constraints.lock \
        -r /tmp/listener-requirements.lock \
        annotated-doc==0.0.5 anyio==4.15.1 pydantic==2.13.5 \
        psycopg==3.3.5 psycopg-binary==3.3.5 typing_extensions==4.16.0 \
    && python -m pip install --no-cache-dir --no-deps --require-hashes \
        -r /tmp/management-http.txt \
    && rm -f /tmp/*-requirements.lock /tmp/management-http.txt \
        /tmp/runtime-constraints.lock

COPY packages/contracts packages/contracts
COPY packages/asset-store packages/asset-store
COPY services/skill-registry services/skill-registry
COPY services/capability-registry services/capability-registry
COPY services/a2ui-composer services/a2ui-composer
COPY services/workflow-composer services/workflow-composer
COPY services/management-api services/management-api
COPY examples/activity-planning examples/activity-planning
COPY deploy/__init__.py deploy/__init__.py
COPY deploy/management deploy/management

RUN groupadd --system --gid ${A2FLOW_GID} a2flow \
    && useradd --system --uid ${A2FLOW_UID} --gid ${A2FLOW_GID} \
        --home-dir /nonexistent --shell /usr/sbin/nologin a2flow

USER ${A2FLOW_UID}:${A2FLOW_GID}
ENTRYPOINT ["python", "-m", "deploy.management.runtime"]
CMD ["serve"]
