FROM python:3.12-slim

COPY f9-revision-proxy.py /opt/f9/f9-revision-proxy.py
RUN chmod 0555 /opt/f9/f9-revision-proxy.py

USER nobody
ENTRYPOINT ["python3", "/opt/f9/f9-revision-proxy.py"]
