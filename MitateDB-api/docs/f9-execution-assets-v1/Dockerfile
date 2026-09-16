# syntax=docker/dockerfile:1.7

FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:slim

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates curl jq nodejs npm python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/mitate-application
COPY --from=app package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY --from=app src ./src
COPY --from=app tsconfig.json tsconfig.build.json ./
RUN npm run build

COPY --from=fixtures . /opt/fixtures
COPY f9-bootstrap-gate.sh f9-isolation-gate.sh f9-auth-curl.sh f9-depth-probe.py f9-json-assert.py f9-job-entrypoint.sh /opt/f9/
RUN chmod 0555 /opt/f9/f9-bootstrap-gate.sh /opt/f9/f9-isolation-gate.sh /opt/f9/f9-auth-curl.sh /opt/f9/f9-depth-probe.py /opt/f9/f9-json-assert.py /opt/f9/f9-job-entrypoint.sh

ENV NODE_ENV=production
ENTRYPOINT ["/opt/f9/f9-job-entrypoint.sh"]
CMD ["gate"]
