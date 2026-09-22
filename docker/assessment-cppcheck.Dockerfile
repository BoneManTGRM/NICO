# Trusted tool provisioning only. No assessed source or credentials enter layers.
FROM gcc:14.2.0-bookworm@sha256:82549aa8f90ada3236a8be70c74543132a76662ef33f0c3271ed802b81584a82
# The build context is the exact official Cppcheck source checkout, never an
# assessed repository. No package install or target execution occurs here.
COPY . /opt/tool-src
RUN test "$(g++ -dumpfullversion)" = 14.2.0 \
    && python3 --version \
    && timeout 180s make -C /opt/tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck 'CXXFLAGS=-O2 -DNDEBUG' \
    && cp /opt/tool-src/cppcheck /usr/local/bin/cppcheck \
    && mkdir -p /opt/cppcheck \
    && cp -R /opt/tool-src/cfg /opt/tool-src/platforms /opt/tool-src/COPYING /opt/cppcheck/ \
    && ln -s /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /opt/tool-src
ENV LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib
USER 1000:1000
ENTRYPOINT ["python"]
