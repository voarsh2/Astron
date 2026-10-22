import os
import shutil
import subprocess
import tempfile
import time


POSTGRES_HOST = '127.0.0.1'
POSTGRES_PORT = '57023'
POSTGRES_STARTUP_TIMEOUT = 30

POSTGRESQL_SETUP_ERROR = """\
Could not find the PostgreSQL server tools on PATH.
Install the PostgreSQL server package and add its bin directory to PATH.
"""


def _wait_for_postgres(postgresd, pg_isready):
    deadline = time.monotonic() + POSTGRES_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if postgresd.poll() is not None:
            raise RuntimeError('PostgreSQL exited during startup')

        result = subprocess.run(
            [pg_isready, '-h', POSTGRES_HOST, '-p', POSTGRES_PORT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(0.25)

    raise RuntimeError('PostgreSQL did not become ready within 30 seconds')


def setup_postgres(unittest):
    postgres = shutil.which('postgres')
    initdb = shutil.which('initdb')
    createuser = shutil.which('createuser')
    createdb = shutil.which('createdb')
    pg_isready = shutil.which('pg_isready')
    if not all((postgres, initdb, createuser, createdb, pg_isready)):
        raise RuntimeError(POSTGRESQL_SETUP_ERROR)

    postgres_path = tempfile.mkdtemp(prefix='astron-', suffix='.postgresql')
    postgresd = None
    try:
        subprocess.run(
            [initdb, '-D', postgres_path, '--auth-local=trust', '--auth-host=trust'],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with open(os.path.join(postgres_path, 'postgresql.conf'), 'a') as config:
            config.write("\nunix_socket_directories = '/tmp'\n")

        log_path = os.path.join(postgres_path, 'postgres.log')
        with open(log_path, 'w') as log_file:
            postgresd = subprocess.Popen(
                [postgres, '-D', postgres_path, '-h', POSTGRES_HOST, '-p', POSTGRES_PORT],
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

        _wait_for_postgres(postgresd, pg_isready)
        subprocess.run(
            [createuser, '-p', POSTGRES_PORT, '-h', POSTGRES_HOST, '--superuser', '--createdb', 'astron'],
            check=True,
        )
        subprocess.run(
            [createdb, '-p', POSTGRES_PORT, '-h', POSTGRES_HOST, '--username=astron', 'astron'],
            check=True,
        )
    except Exception as error:
        if postgresd is not None and postgresd.poll() is None:
            postgresd.terminate()
            postgresd.wait()
        try:
            with open(os.path.join(postgres_path, 'postgres.log'), 'r') as log_file:
                details = log_file.read().strip()
            if details:
                error.args = ('%s\n%s' % (error, details),)
        except OSError:
            pass
        shutil.rmtree(postgres_path, ignore_errors=True)
        raise

    unittest.postgres_path = postgres_path
    unittest.postgresd = postgresd


def teardown_postgres(unittest):
    postgresd = getattr(unittest, 'postgresd', None)
    if postgresd is not None and postgresd.poll() is None:
        postgresd.terminate()
        try:
            postgresd.wait(timeout=10)
        except subprocess.TimeoutExpired:
            postgresd.kill()
            postgresd.wait()

    postgres_path = getattr(unittest, 'postgres_path', None)
    if postgres_path is not None:
        shutil.rmtree(postgres_path, ignore_errors=True)
