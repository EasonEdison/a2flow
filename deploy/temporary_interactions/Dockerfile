ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG SOURCE_REVISION
USER root
COPY services/agent-workflow-runtime/src/agent_workflow_runtime /opt/a2flow/services/agent-workflow-runtime/src/agent_workflow_runtime
COPY services/b-side-api/src/a2flow_bside /opt/a2flow/services/b-side-api/src/a2flow_bside
COPY services/a2ui-execution/src/a2flow_a2ui /opt/a2flow/services/a2ui-execution/src/a2flow_a2ui
COPY services/capability-execution/src/a2flow_capability /opt/a2flow/services/capability-execution/src/a2flow_capability
COPY packages/rpc-contracts/src /opt/a2flow/packages/rpc-contracts/src
RUN printf '%s\n' /opt/a2flow/services/a2ui-execution/src /opt/a2flow/services/capability-execution/src /opt/a2flow/packages/rpc-contracts/src > /usr/local/lib/python3.11/site-packages/a2flow-temporary.pth
LABEL org.opencontainers.image.revision="${SOURCE_REVISION}"
USER 1000:1000
