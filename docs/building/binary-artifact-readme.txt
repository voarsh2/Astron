Astron binary package
=====================

This archive contains astrond and its non-system runtime libraries. Keep all
included libraries with astrond when extracting the package. Astron's
configuration files and database server programs are not included.

The Linux archive is built for x86_64 on Ubuntu 24.04. It includes the YAML,
MongoDB, and PostgreSQL backends. It needs a compatible Linux system runtime;
the system C library is supplied by the host.

The macOS archive is built on macOS 15 for the runner's architecture. It
includes the YAML and MongoDB backends. Apple system frameworks are supplied by
macOS.

The Windows archive is built for x64 and includes the YAML and MongoDB
backends, plus the vcpkg runtime DLLs.

MongoDB and PostgreSQL database servers are separate services and must be
installed and configured separately when using those backends.
