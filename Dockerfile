# Dockerfile for Building and Running Astron

# Keep the fork's container-based build workflow. MongoDB support is optional
# and remains disabled by default because the old libmongoclient-dev package
# is obsolete.
FROM ubuntu:latest

ARG TARGET=linux
ARG BUILD_TYPE=Release
ARG BUILD_DB_MONGO=OFF
ARG VCPKG_TARGET_TRIPLET=x64-mingw-static
ARG STATIC_RUNTIME=ON

RUN apt-get update && \
    apt-get install -y \
    cmake \
    libyaml-cpp-dev \
    llvm \
    libboost-dev \
    clang \
    g++ \
    gcc \
    libuv1-dev

RUN if [ "${TARGET}" = "windows" ]; then \
        apt-get update && \
        apt-get install -y \
            binutils-mingw-w64-x86-64 \
            curl \
            g++-mingw-w64-x86-64 \
            git \
            ninja-build \
            pkg-config \
            tar \
            unzip \
            zip && \
        git clone --depth 1 https://github.com/microsoft/vcpkg.git /opt/vcpkg && \
        /opt/vcpkg/bootstrap-vcpkg.sh -disableMetrics && \
        /opt/vcpkg/vcpkg install \
            boost-icl:${VCPKG_TARGET_TRIPLET} \
            libuv:${VCPKG_TARGET_TRIPLET} \
            yaml-cpp:${VCPKG_TARGET_TRIPLET} && \
        if [ "${BUILD_DB_MONGO}" = "ON" ]; then \
            /opt/vcpkg/vcpkg install mongo-cxx-driver:${VCPKG_TARGET_TRIPLET}; \
        fi; \
    fi

# Copy this checkout, including its current working-tree changes, into the
# build container.
COPY . /app-src
WORKDIR /app-src

RUN mkdir -p /app/build /app/package/lib /app/package/tests /app/package/include/astron && \
    cd /app/build && \
    if [ "${TARGET}" = "windows" ]; then \
        if [ "${STATIC_RUNTIME}" = "OFF" ]; then \
            CXX_FLAGS=''; \
            LINKER_FLAGS=''; \
        else \
            CXX_FLAGS='-static-libgcc -static-libstdc++'; \
            LINKER_FLAGS='-static'; \
        fi; \
        cmake -G Ninja \
              -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
              -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
              -DCMAKE_SYSTEM_NAME=Windows \
              -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc-posix \
              -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++-posix \
              -DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres \
              -DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake \
              -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET} \
              -DVCPKG_HOST_TRIPLET=x64-linux \
              -DBUILD_DB_MONGO=${BUILD_DB_MONGO} \
              -DCMAKE_CXX_FLAGS="${CXX_FLAGS}" \
              -DCMAKE_EXE_LINKER_FLAGS="${LINKER_FLAGS}" /app-src; \
    else \
        cmake -DCMAKE_BUILD_TYPE=${BUILD_TYPE} \
              -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
              -DBUILD_DB_MONGO=${BUILD_DB_MONGO} /app-src; \
    fi && \
    cmake --build . --parallel "$(nproc)" && \
    if [ "${TARGET}" = "windows" ]; then \
        cp astrond.exe /app/astrond.exe; \
        cp astrond.exe /app/package/astrond.exe; \
    else \
        cp astrond /app/astrond; \
        cp astrond /app/package/astrond; \
    fi && \
    cp libastron.a /app/package/lib/libastron.a && \
    cp src/dclass/libdclass.a /app/package/lib/libdclass.a && \
    cp /app-src/src/local/astron_embed.h /app/package/include/astron/astron_embed.h && \
    for tool in test_poll_pause test_local_embed astron_local_host; do \
        for suffix in "" .exe; do \
            if [ -f "${tool}${suffix}" ]; then \
                cp "${tool}${suffix}" /app/package/tests/; \
            fi; \
        done; \
    done && \
    if [ "${TARGET}" = "windows" ] && [ -d "/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}/bin" ]; then \
        find "/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}/bin" -maxdepth 1 -type f -iname '*.dll' -exec cp {} /app/package/ \;; \
    fi && \
    printf 'target=%s\nbuild_type=%s\nbuild_db_mongo=%s\nvcpkg_target_triplet=%s\nstatic_runtime=%s\n' \
        "${TARGET}" "${BUILD_TYPE}" "${BUILD_DB_MONGO}" "${VCPKG_TARGET_TRIPLET}" "${STATIC_RUNTIME:-ON}" \
        > /app/package/BUILD-INFO.txt && \
    rm -rf /app-src /app/build

WORKDIR /app
COPY startup.sh .
RUN chmod +x startup.sh
ENTRYPOINT ["./startup.sh"]
