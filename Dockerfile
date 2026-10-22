FROM ubuntu:24.04 AS build-base

ARG ASTRON_GIT_SHA

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bison \
        build-essential \
        cmake \
        flex \
        libboost-dev \
        libuv1-dev \
        libyaml-cpp-dev \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .

FROM build-base AS build-postgresql

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        libsoci-dev \
        libsoci-postgresql4.0 \
    && rm -rf /var/lib/apt/lists/* \
    && cmake -S . -B /tmp/astron-build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DASTRON_REGENERATE_DC_PARSER=ON \
        -DBUILD_DB_POSTGRESQL=ON \
        -DASTRON_GIT_SHA="${ASTRON_GIT_SHA}" \
    && cmake --build /tmp/astron-build --parallel

FROM ubuntu:24.04 AS mongo-driver

ARG MONGOCXX_VERSION=4.6.0

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libicu-dev \
        libsnappy-dev \
        libssl-dev \
        libsasl2-dev \
        libzstd-dev \
        ninja-build \
        pkg-config \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch "r${MONGOCXX_VERSION}" \
        https://github.com/mongodb/mongo-cxx-driver.git /tmp/mongo-cxx-driver \
    && cmake -S /tmp/mongo-cxx-driver -B /tmp/mongo-cxx-build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_STANDARD=17 \
        -DCMAKE_INSTALL_PREFIX=/opt/mongodb \
        -DBUILD_VERSION="${MONGOCXX_VERSION}" \
        -DENABLE_TESTS=OFF \
        -DBUILD_TESTING=OFF \
    && cmake --build /tmp/mongo-cxx-build --parallel 4 \
    && cmake --install /tmp/mongo-cxx-build

FROM mongo-driver AS mongo-runtime-libs

RUN mkdir -p /tmp/mongo-runtime/lib \
    && cp -a /opt/mongodb/lib/libmongocxx1.so.* \
        /opt/mongodb/lib/libbsoncxx1.so.* \
        /opt/mongodb/lib/libmongoc2.so.* \
        /opt/mongodb/lib/libbson2.so.* \
        /tmp/mongo-runtime/lib/

FROM build-base AS build-mongodb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libsasl2-dev \
        libsnappy1v5 \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mongo-driver /opt/mongodb /opt/mongodb

RUN cmake -S . -B /tmp/astron-build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DASTRON_REGENERATE_DC_PARSER=ON \
        -DCMAKE_PREFIX_PATH=/opt/mongodb \
        -DBUILD_DB_MONGO=ON \
        -DASTRON_GIT_SHA="${ASTRON_GIT_SHA}" \
    && cmake --build /tmp/astron-build --parallel

FROM ubuntu:24.04 AS runtime-base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libuv1t64 \
        libyaml-cpp0.8 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --home-dir /var/lib/astron --shell /usr/sbin/nologin astron \
    && mkdir -p /etc/astron /var/lib/astron/database \
    && chown -R astron:astron /var/lib/astron

WORKDIR /var/lib/astron
EXPOSE 6660 6667
ENTRYPOINT ["astrond"]
CMD ["-l", "info", "/etc/astron/astron.yml"]

FROM runtime-base AS runtime-postgresql

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        libsoci-core4.0 \
        libsoci-postgresql4.0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build-postgresql /tmp/astron-build/astrond /usr/local/bin/astrond
COPY docker/astron.yml /etc/astron/astron.yml
COPY docker/astron-yaml.yml /etc/astron/astron-yaml.yml
USER astron

FROM runtime-base AS runtime-mongodb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libicu74 \
        libsnappy1v5 \
        libssl3t64 \
        libsasl2-2 \
        libzstd1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mongo-runtime-libs /tmp/mongo-runtime/lib /opt/mongodb/lib
RUN echo /opt/mongodb/lib > /etc/ld.so.conf.d/mongodb.conf && ldconfig
COPY --from=build-mongodb /tmp/astron-build/astrond /usr/local/bin/astrond
COPY docker/astron-mongo.yml /etc/astron/astron-mongo.yml
COPY docker/astron-yaml.yml /etc/astron/astron-yaml.yml
USER astron
CMD ["-l", "info", "/etc/astron/astron-mongo.yml"]

FROM runtime-postgresql AS runtime
CMD ["-l", "info", "/etc/astron/astron-yaml.yml"]
