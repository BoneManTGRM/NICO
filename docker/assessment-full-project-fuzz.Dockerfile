# Build only the pinned upstream tool dependency; never assessed repository code.
FROM gcc:14.2.0-bookworm@sha256:82549aa8f90ada3236a8be70c74543132a76662ef33f0c3271ed802b81584a82 AS capnp-builder
COPY capnp-source /opt/capnp-inputs
COPY cmake.whl /opt/cmake.whl
RUN cd /opt/capnp-inputs && sha256sum -c SHA256SUMS \
    && echo '1c8b05df0602365da91ee6a3336fe57525b137706c4ab5675498f662ae1dbcec  /opt/cmake.whl' | sha256sum -c - \
    && python3 -m zipfile -e /opt/cmake.whl /opt/cmake-wheel \
    && chmod 755 /opt/cmake-wheel/cmake/data/bin/cmake \
    && mkdir /opt/capnp-source \
    && tar --extract --gzip --file=capnproto.tar.gz --directory=/opt/capnp-source --strip-components=1 --no-same-owner --no-same-permissions \
    && /opt/cmake-wheel/cmake/data/bin/cmake -S /opt/capnp-source -B /opt/capnp-build \
       -DBUILD_TESTING=OFF -DWITH_OPENSSL=OFF -DWITH_ZLIB=OFF \
       -DBUILD_SHARED_LIBS=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
       -DCMAKE_BUILD_TYPE=Release '-DCMAKE_CXX_FLAGS_RELEASE=-O1 -DNDEBUG' \
       -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_INSTALL_LIBDIR=lib \
    && timeout 180s /opt/cmake-wheel/cmake/data/bin/cmake --build /opt/capnp-build --parallel 2 \
    && DESTDIR=/opt/capnp-install /opt/cmake-wheel/cmake/data/bin/cmake --install /opt/capnp-build \
    && test "$(LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib /opt/capnp-install/usr/local/bin/capnp --version)" = "Cap'n Proto version 1.5.0" \
    && mkdir /opt/nico-capnp-metadata \
    && cp lock.json receipt.json SHA256SUMS /opt/nico-capnp-metadata/

# Build the trusted observer with SDK headers; retain only its small runtime artifact.
FROM gcc:14.2.0-bookworm@sha256:82549aa8f90ada3236a8be70c74543132a76662ef33f0c3271ed802b81584a82 AS clang-header-builder
COPY llvm /opt/llvm-inputs
COPY clang-header-sdk /opt/clang-header-sdk
COPY clang-header-evidence /opt/clang-header-evidence
COPY build_cpp_clang_header_observer.py /opt/build_cpp_clang_header_observer.py
RUN cd /opt/llvm-inputs && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && cd /opt/clang-header-sdk && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && timeout 180s python3 /opt/build_cpp_clang_header_observer.py \
       --source /opt/clang-header-evidence --sdk /opt/clang-header-sdk \
       --runtime /opt/llvm-inputs --output /opt/clang-header-built

# Trusted pinned tools only. Assessed source enters the disposable runtime, never a layer.
FROM gcc:14.2.0-bookworm@sha256:82549aa8f90ada3236a8be70c74543132a76662ef33f0c3271ed802b81584a82
COPY project-dependencies /opt/project-dependency-inputs
COPY llvm /opt/llvm-inputs
COPY cppcheck /opt/tool-src
COPY repair_cppcheck_placement_ast.py /opt/repair_cppcheck_placement_ast.py
COPY repair_cppcheck_header_grammar.py /opt/repair_cppcheck_header_grammar.py
COPY patch_cppcheck_header_evidence.py /opt/patch_cppcheck_header_evidence.py
COPY cppcheck-header-evidence /opt/cppcheck-header-evidence
COPY verify_cpp_runtime_toolchain.py /opt/verify_cpp_runtime_toolchain.py
COPY cmake.whl /opt/cmake.whl
COPY pycapnp.whl /opt/pycapnp.whl
COPY runtime-dependencies/payload /opt/nico-runtime
COPY runtime-dependencies/lock.json runtime-dependencies/receipt.json runtime-dependencies/SHA256SUMS /opt/nico-runtime-inputs/
RUN cd /opt/nico-runtime && sha256sum -c /opt/nico-runtime-inputs/SHA256SUMS
RUN cd /opt/project-dependency-inputs && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && mkdir -p /opt/nico-project-dependencies \
    && cp lock.json receipt.json SHA256SUMS /opt/nico-project-dependencies/ \
    && cd / && rm -rf /opt/project-dependency-inputs \
    && cd /opt/llvm-inputs && sha256sum -c SHA256SUMS \
    && for package in *.deb; do dpkg-deb --extract "$package" /; done \
    && test "$(/usr/lib/llvm-17/bin/clang -dumpversion)" = 17.0.6 \
    && cd / && rm -rf /opt/llvm-inputs \
    && test "$(g++ -dumpfullversion)" = 14.2.0 \
    && python3 /opt/repair_cppcheck_placement_ast.py /opt/tool-src/lib/tokenlist.cpp > /opt/nico-cppcheck-repair.json \
    && python3 /opt/repair_cppcheck_header_grammar.py /opt/tool-src > /opt/nico-cppcheck-header-grammar.json \
    && python3 /opt/patch_cppcheck_header_evidence.py /opt/tool-src /opt/cppcheck-header-evidence > /opt/nico-cppcheck-header-observer.json \
    && timeout 180s make -C /opt/tool-src -j2 MATCHCOMPILER=yes FILESDIR=/opt/cppcheck 'CXXFLAGS=-O2 -DNDEBUG' \
    && cp /opt/tool-src/cppcheck /usr/local/bin/cppcheck \
    && mkdir -p /opt/cppcheck \
    && cp -R /opt/tool-src/cfg /opt/tool-src/platforms /opt/tool-src/COPYING /opt/cppcheck/ \
    && echo '1c8b05df0602365da91ee6a3336fe57525b137706c4ab5675498f662ae1dbcec  /opt/cmake.whl' | sha256sum -c - \
    && echo 'd682ae9f23a0c6568533ca2ebf6d70ac7e599dd222f671fa87dff278de343eec  /opt/pycapnp.whl' | sha256sum -c - \
    && python3 -m zipfile -e /opt/cmake.whl /opt/cmake-wheel \
    && mkdir -p /opt/pycapnp \
    && python3 -m zipfile -e /opt/pycapnp.whl /opt/pycapnp \
    && chmod 755 /opt/cmake-wheel/cmake/data/bin/cmake /opt/cmake-wheel/cmake/data/bin/ctest \
    && ln -s /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /opt/tool-src /opt/cmake.whl /opt/pycapnp.whl
COPY --from=capnp-builder /opt/capnp-install/usr/local/ /usr/local/
COPY --from=capnp-builder /opt/nico-capnp-metadata/ /opt/nico-capnp/
COPY --from=clang-header-builder /opt/clang-header-built/observer.so /opt/nico-clang-header-observer.so
COPY --from=clang-header-builder /opt/clang-header-built/receipt.json /opt/nico-clang-header-observer.json
COPY --from=clang-header-builder /opt/clang-header-built/startup-control.json /opt/nico-clang-header-startup/control.json
COPY --from=clang-header-builder /opt/clang-header-built/probe.cpp /opt/nico-clang-header-startup/probe.cpp
COPY --from=clang-header-builder /opt/clang-header-built/probe.header.json /opt/nico-clang-header-startup/probe.header.json
COPY --from=clang-header-builder /opt/clang-header-built/probe.plist /opt/nico-clang-header-startup/probe.plist
ENV PATH=/opt/cmake-wheel/cmake/data/bin:/usr/local/bin:/usr/bin:/bin
ENV PYTHONPATH=/opt/pycapnp
ENV PREVIOUS_RELEASES_DIR=/opt/nico-runtime/previous-releases
ENV LD_LIBRARY_PATH=/usr/local/lib64:/usr/local/lib
# Clang must use the headers and runtime that built the pinned static libraries.
# Its default distribution search selects /usr's GCC instead of /usr/local's GCC 14.
RUN printf '%s\n' '--gcc-toolchain=/usr/local' > /usr/lib/llvm-17/bin/clang.cfg \
    && cp /usr/lib/llvm-17/bin/clang.cfg /usr/lib/llvm-17/bin/clang++.cfg \
    && timeout 30s python3 /opt/verify_cpp_runtime_toolchain.py > /opt/nico-cpp-runtime-toolchain.json \
       || { cat /opt/nico-cpp-runtime-toolchain.json; exit 1; }
RUN python3 -c "import capnp; assert capnp.__version__ == '2.2.1'"
LABEL org.nico.cppcheck.repair="placement-new-initializer-ast-v1"
USER 1000:1000
# Standalone worker controls override ENTRYPOINT with python -I -S. Validate
# that exact interpreter contract as the runtime user before publishing a layer.
RUN python -I -S -c "import os, sys; assert sys.version_info.major == 3; assert sys.flags.isolated and sys.flags.no_site; assert (os.getuid(), os.getgid()) == (1000, 1000)"
ENTRYPOINT ["sleep"]

LABEL org.nico.cppcheck.header-grammar="physical-header-grammar-v1"
