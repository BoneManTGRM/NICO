# Trusted tool provisioning only. No assessed source or credentials enter layers.
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
COPY cppcheck /usr/local/bin/cppcheck
COPY cfg /opt/cppcheck/cfg
COPY platforms /opt/cppcheck/platforms
COPY COPYING /opt/cppcheck/COPYING
COPY libstdc++.so.6 libgcc_s.so.1 /usr/local/lib/
ENV LD_LIBRARY_PATH=/usr/local/lib
USER 1000:1000
ENTRYPOINT ["python"]
