# Draft only. Supply independently verified linux/amd64 official digests.
ARG PYTHON_IMAGE
ARG POSTGRES_IMAGE
FROM ${PYTHON_IMAGE} AS python_runtime
COPY wheels/ /wheelhouse/
COPY requirements.lock /tmp/requirements.lock
RUN --network=none python3 -m pip --isolated install --no-index --no-deps \
    --only-binary=:all: --require-hashes --no-compile --find-links=/wheelhouse \
    -r /tmp/requirements.lock && python3 -m pip --isolated check

FROM ${POSTGRES_IMAGE}
COPY --from=python_runtime /usr/local/ /opt/nico-python/
COPY native-source/ /opt/nico-reader/native-source/
COPY native-source-manifest.json native_reader.py native_pg18_driver.py native_import_probe.py synthetic_fixture.py /opt/nico-reader/
COPY runner.sh qualify.py /opt/nico-reader/
RUN --network=none /bin/bash -n /opt/nico-reader/runner.sh && \
    env -i PATH=/usr/bin:/bin PYTHONHOME=/opt/nico-python \
      LD_LIBRARY_PATH=/opt/nico-python/lib PYTHONDONTWRITEBYTECODE=1 \
      /opt/nico-python/bin/python3 /opt/nico-reader/qualify.py
ENTRYPOINT ["/usr/bin/timeout","--signal=TERM","--kill-after=30s","90s","/bin/bash","/opt/nico-reader/runner.sh"]
