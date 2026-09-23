# Trusted pinned tools only. Assessed source enters the disposable runtime, never a layer.
FROM gcc:14.2.0-bookworm@sha256:82549aa8f90ada3236a8be70c74543132a76662ef33f0c3271ed802b81584a82
COPY project-dependencies /opt/project-dependency-inputs
COPY llvm /opt/llvm-inputs
COPY cppcheck /opt/tool-src
COPY cmake.whl /opt/cmake.whl
RUN cd /opt/project-dependency-inputs && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && mkdir -p /opt/nico-project-dependencies \
    && cp receipt.json SHA256SUMS /opt/nico-project-dependencies/ \
    && cd / && rm -rf /opt/project-dependency-inputs \
    && cd /opt/llvm-inputs && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && test "$(/usr/lib/llvm-17/bin/clang -dumpversion)" = 17.0.6 \
    && cd / && rm -rf /opt/llvm-inputs \
    && test "$(g++ -dumpfullversion)" = 14.2.0 \
    && timeout 180s make -C /opt/tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck 'CXXFLAGS=-O2 -DNDEBUG' \
    && cp /opt/tool-src/cppcheck /usr/local/bin/cppcheck \
    && mkdir -p /opt/cppcheck \
    && cp -R /opt/tool-src/cfg /opt/tool-src/platforms /opt/tool-src/COPYING /opt/cppcheck/ \
    && echo '1c8b05df0602365da91ee6a3336fe57525b137706c4ab5675498f662ae1dbcec  /opt/cmake.whl' | sha256sum -c - \
    && python3 -m zipfile -e /opt/cmake.whl /opt/cmake-wheel \
    && chmod 755 /opt/cmake-wheel/cmake/data/bin/cmake /opt/cmake-wheel/cmake/data/bin/ctest \
    && rm -rf /opt/tool-src /opt/cmake.whl
ENV PATH=/opt/cmake-wheel/cmake/data/bin:/usr/local/bin:/usr/bin:/bin
ENV LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib
USER 1000:1000
ENTRYPOINT ["sleep"]
