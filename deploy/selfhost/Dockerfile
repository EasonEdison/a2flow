# Build from the repository root. No private/pre-existing A2Flow image is required.
FROM node:22-bookworm-slim AS employee-build
WORKDIR /build
COPY apps/digital-employee/web/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY apps/digital-employee/web/ ./
RUN npm run build

FROM node:22-bookworm-slim AS management-web-build
WORKDIR /build
COPY services/management-java/frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY services/management-java/frontend/ ./
RUN npm run build

FROM maven:3.9-eclipse-temurin-17 AS java-build
WORKDIR /build
COPY services/management-java/ ./
RUN mvn --batch-mode --no-transfer-progress -DskipTests compile dependency:copy-dependencies

FROM python:3.11.14-slim-bookworm AS python
WORKDIR /opt/a2flow
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY experiments/runtime-phase1/requirements.lock /tmp/runtime.lock
COPY deploy/mvp/model-requirements.lock /tmp/model.lock
COPY deploy/mvp/listener-requirements.lock /tmp/listener.lock
COPY services/agent-workflow-runtime/requirements-http.txt /tmp/http.lock
# Use the scheduler-reviewed PostgreSQL driver consistently across all roles.
RUN sed -i 's/^psycopg==3.3.5$/psycopg==3.3.6/;s/^psycopg-binary==3.3.5$/psycopg-binary==3.3.6/' /tmp/runtime.lock \
    && python -m pip install --no-cache-dir -r /tmp/runtime.lock -r /tmp/model.lock -r /tmp/listener.lock \
    && python -m pip install --no-cache-dir --no-deps --require-hashes -r /tmp/http.lock \
    && python -m pip install --no-cache-dir -c /tmp/runtime.lock \
      SQLAlchemy==2.0.54 redis==5.3.1 croniter==6.0.0 jsonschema==4.26.0 \
      markdown-it-py==4.2.0 mdurl==0.1.2 grpcio==1.75.1 'protobuf>=6.31.1,<7' setuptools wheel
COPY packages/ packages/
COPY services/ services/
COPY examples/ examples/
COPY deploy/ deploy/
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation \
      ./packages/rpc-contracts ./services/capability-execution ./services/a2ui-execution ./services/content-service
ENV PYTHONPATH=/opt/a2flow/packages/contracts/src:/opt/a2flow/packages/asset-store/src:/opt/a2flow/services/skill-registry/src:/opt/a2flow/services/capability-registry/src:/opt/a2flow/services/a2ui-composer/src:/opt/a2flow/services/b-side-api/src:/opt/a2flow/services/scheduler-mq/src:/opt/a2flow/services/agent-workflow-runtime/src:/opt/a2flow/examples/activity-planning
COPY --from=employee-build /build/dist /opt/a2flow/static/employee
ENTRYPOINT ["python", "-m", "deploy.selfhost.launcher"]

FROM eclipse-temurin:17-jre-jammy AS management
WORKDIR /opt/management
COPY --from=java-build /build/target/classes ./classes
COPY --from=java-build /build/target/dependency ./dependency
COPY --from=management-web-build /build/dist /opt/management-static
COPY deploy/selfhost/java-entrypoint.sh /opt/management/entrypoint.sh
RUN chmod -R a+rX /opt/management /opt/management-static
ENTRYPOINT ["sh", "/opt/management/entrypoint.sh"]

FROM nginx:1.28-alpine AS gateway
COPY deploy/selfhost/nginx.conf /etc/nginx/nginx.conf
COPY deploy/people_selection/ /opt/examples/people-selection/
COPY deploy/reading_content/ /opt/examples/reading-content/
COPY --from=management-web-build /build/dist /opt/management-static
COPY --from=employee-build /build/dist /opt/employee-static
