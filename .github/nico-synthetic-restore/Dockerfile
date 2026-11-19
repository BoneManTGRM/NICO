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
# The context is local-0700; publish read-only code to the fixture users in
# this image only. The seed and read processes must not run as root.
RUN --network=none find /opt/nico-reader -type d -exec chmod 0555 {} + && \
    find /opt/nico-reader -type f -exec chmod 0444 {} + && \
    /bin/bash -n /opt/nico-reader/runner.sh && \
    env -i PATH=/usr/bin:/bin PYTHONHOME=/opt/nico-python \
      LD_LIBRARY_PATH=/opt/nico-python/lib PYTHONDONTWRITEBYTECODE=1 \
      /opt/nico-python/bin/python3 /opt/nico-reader/qualify.py && \
    env -i PATH=/usr/local/bin:/usr/bin:/bin PYTHONHOME=/opt/nico-python \
      LD_LIBRARY_PATH=/opt/nico-python/lib PYTHONDONTWRITEBYTECODE=1 \
      gosu nobody /opt/nico-python/bin/python3 /opt/nico-reader/native_import_probe.py
ENTRYPOINT ["/usr/bin/timeout","--signal=TERM","--kill-after=30s","90s","/bin/bash","/opt/nico-reader/runner.sh"]
