# Fake-only candidate. Fixed official linux/amd64 bases from proven CI.
FROM docker.io/library/python:3.13.18-slim-bookworm@sha256:f3dac913ab53b78c64f26d5518fcd7043d5a1a46522d6a493b598c3ed12f62a6 AS python_runtime
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip --isolated download --index-url https://pypi.org/simple \
    --no-deps --no-cache-dir --require-hashes --only-binary=:all: \
    --platform manylinux_2_28_x86_64 --platform manylinux_2_27_x86_64 \
    --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 \
    --abi cp313 -r /tmp/requirements.lock -d /wheelhouse
RUN --network=none python3 -m pip --isolated install --no-index --no-deps \
    --only-binary=:all: --require-hashes --no-compile --find-links=/wheelhouse \
    -r /tmp/requirements.lock && python3 -m pip --isolated check

FROM docker.io/library/postgres:18.6-bookworm@sha256:02fb3245e038f33536cf13bc6c4e59f21d07b0cea3c1fe1c07c6e8aa8f083bcc
COPY --from=python_runtime /usr/local/ /opt/nico-python/
COPY native-source/ /opt/nico-reader/native-source/
COPY native-source-manifest.json native_reader.py native_pg18_driver.py native_import_probe.py synthetic_fixture.py /opt/nico-reader/
COPY runner.sh qualify.py stream_frame.sh stream_replay.py stream_restore.py /opt/nico-reader/
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
