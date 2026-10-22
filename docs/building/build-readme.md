How to Build Astron
------------------

### Getting a copy of the code ###

    git clone https://github.com/Astron/Astron.git
    cd Astron

### Toolchain and dependencies ###

Astron uses C++17 and CMake 3.18 or newer. The Linux build uses GCC or Clang,
Boost headers (ICL), libuv, and yaml-cpp. On Ubuntu 24.04, install them with:

    sudo apt-get update
    sudo apt-get install build-essential cmake ninja-build bison flex \
        libboost-dev libuv1-dev libyaml-cpp-dev

Linux builds regenerate the DC parser using Bison and Flex in the build
directory. Set `-DASTRON_REGENERATE_DC_PARSER=OFF` to use the generated parser
sources already included in the repository.

### Build ###

Use an out-of-source build directory. The example puts all compiler output in
`/tmp`, which is useful when the source workspace has limited storage:

    cmake -S . -B /tmp/astron-build -G Ninja \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DASTRON_REGENERATE_DC_PARSER=ON
    cmake --build /tmp/astron-build --parallel

### Database backends ###

The YAML backend is enabled by default and is intended for development. The
PostgreSQL backend uses SOCI 4 and libpq. On Ubuntu 24.04, install its packages
and enable it during configuration:

    sudo apt-get install libsoci-dev libsoci-postgresql4.0 libpq-dev
    cmake -S . -B /tmp/astron-build -G Ninja \
        -DBUILD_DB_POSTGRESQL=ON
    cmake --build /tmp/astron-build --parallel

SQLite and MySQL backends can also be selected with `BUILD_DB_SQLITE` and
`BUILD_DB_MYSQL`; each requires the matching SOCI backend package. MongoDB is
available as an optional backend with MongoDB C++ Driver 4.4 or newer
(`BUILD_DB_MONGO=ON`). Set `CMAKE_PREFIX_PATH` if the driver is installed outside
the system package paths. CI builds against driver 4.6.0.

### Containers ###

The Docker image builds in a separate stage and runs as an unprivileged user.
Docker Compose starts Astron with the YAML database by default:

    docker compose up --build

To use PostgreSQL, start its profile explicitly:

    docker compose --profile postgresql up --build astron-postgresql postgres

To build and start the MongoDB image and server:

    docker compose --profile mongodb up --build astron-mongodb mongodb

To run an image published from a fork branch, set its SHA-tagged image first:

    ASTRON_IMAGE=ghcr.io/owner/repo:sha docker compose up --pull always --no-build
    ASTRON_IMAGE=ghcr.io/owner/repo:sha docker compose --profile postgresql up \
        --pull always --no-build astron-postgresql postgres
    ASTRON_MONGODB_IMAGE=ghcr.io/owner/repo:mongodb-sha docker compose --profile mongodb up \
        --pull always --no-build astron-mongodb mongodb

The YAML, PostgreSQL, and MongoDB Astron services share the same public ports;
run one Astron service at a time. When selecting a profile, name the desired
Astron and database services explicitly so Compose does not also start the
default YAML service.

These Compose configs are starter topologies and do not include application-
specific `general.dc_files`. Use a Compose override to mount your config and DC
files under `/etc/astron`, then point `general.dc_files` at the mounted files.

The example PostgreSQL credentials in `compose.yaml` and `docker/astron.yml`
are for local development. Change both before deploying beyond a local setup.

### Windows ###

See the [Visual Studio guide](windows-visualstudio.md). Windows uses the
generated parser files checked into the repository by default. The GitHub
Actions Windows job installs Boost ICL, libuv, yaml-cpp, and the MongoDB C++
driver with vcpkg, builds and runs the integration suite with CTest, and uploads
the executable with its vcpkg runtime DLLs as the `astron-windows-x64` artifact.

### Continuous integration ###

GitHub Actions builds and tests Linux with GCC and Clang, macOS, and Windows.
Linux exercises YAML, MongoDB, and PostgreSQL; macOS and Windows exercise YAML
and MongoDB. The Linux job also builds the MongoDB driver using the same Docker
build stage used by the MongoDB image. CTest runs sequentially because the
integration tests use fixed local ports. After each platform's tests pass, CI
uploads a Windows ZIP, Linux x86_64 tarball, and macOS tarball with their
non-system runtime libraries. The database server programs themselves remain
separate services.

Workflow artifacts use the repository's configured retention period. Successful
builds of the default branch are also published as assets on the rolling
`latest-main` prerelease, which does not expire with Actions artifacts. Successful
`v*` tag builds publish the same packages on that version's GitHub Release.
The publisher uses the workflow's built-in `GITHUB_TOKEN` with `contents: write`,
so it needs no repository secrets. Repository rules must allow the workflow to
move the `latest-main` tag and replace that prerelease's assets.
