# Extend the reviewed SDK image, retaining its locked Agent/model dependencies.
ARG SDK_IMAGE
FROM ${SDK_IMAGE}
USER root
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY packages/rpc-contracts /opt/a2flow/packages/rpc-contracts
COPY services/capability-execution /opt/a2flow/services/capability-execution
COPY services/a2ui-execution /opt/a2flow/services/a2ui-execution
COPY services/content-service /opt/a2flow/services/content-service
RUN python -m pip install --no-cache-dir --index-url ${PIP_INDEX_URL} \
      markdown-it-py==4.2.0 mdurl==0.1.2 \
    && python -m pip install --no-cache-dir --no-deps --no-build-isolation \
      /opt/a2flow/packages/rpc-contracts \
      /opt/a2flow/services/capability-execution \
      /opt/a2flow/services/a2ui-execution \
      /opt/a2flow/services/content-service
USER 1000:1000
ENTRYPOINT ["python"]
CMD ["-m", "a2flow_a2ui"]
