# Reuse the already installed SDK environment; source is from the reviewed SHA.
ARG SDK_IMAGE=a2flow-attended:af13
FROM ${SDK_IMAGE}
USER root
# Remove retired sources inherited from older SDK images before copying this SHA.
RUN rm -rf /opt/a2flow/services/management-api \
    /opt/a2flow/services/workflow-composer /opt/a2flow/deploy/management \
    /opt/a2flow/services/a2ui-composer/src/a2ui_composer \
    /opt/a2flow/services/capability-registry/src/capability_registry
ENV PYTHONPATH=/opt/a2flow/packages/contracts/src:/opt/a2flow/packages/asset-store/src:/opt/a2flow/services/skill-registry/src:/opt/a2flow/services/capability-registry/src:/opt/a2flow/services/a2ui-composer/src:/opt/a2flow/services/b-side-api/src:/opt/a2flow/services/scheduler-mq/src:/opt/a2flow/services/agent-workflow-runtime/src:/opt/a2flow/examples/activity-planning

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY services/b-side-api/requirements-db.txt /tmp/bside-db.txt
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} -r /tmp/bside-db.txt
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} jsonschema==4.26.0
COPY packages /opt/a2flow/packages
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} /opt/a2flow/packages/rpc-contracts
COPY services /opt/a2flow/services
COPY examples/activity-planning /opt/a2flow/examples/activity-planning
COPY deploy /opt/a2flow/deploy
USER 1000:1000
ENTRYPOINT ["python", "-m", "deploy.realchat.launcher"]
