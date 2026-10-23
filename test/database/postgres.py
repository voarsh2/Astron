import os
import shutil
import subprocess
import tempfile

from common.process_output import ProcessOutput


POSTGRES_HOST = '127.0.0.1'
POSTGRES_PORT = '57023'
POSTGRES_STARTUP_TIMEOUT = 30

POSTGRESQL_SETUP_ERROR = """\
Could not find the PostgreSQL server tools on PATH.
Install the PostgreSQL server package and add its bin directory to PATH.
"""


def _wait_for_postgres(output):
    output.wait_for_any(
        ('database system is ready to accept connections',),
        POSTGRES_STARTUP_TIMEOUT,
        'PostgreSQL',
    )


def setup_postgres(unittest):
    postgres = shutil.which('postgres')
    initdb = shutil.which('initdb')
    createuser = shutil.which('createuser')
    createdb = shutil.which('createdb')
    if not all((postgres, initdb, createuser, createdb)):
        raise RuntimeError(POSTGRESQL_SETUP_ERROR)

    postgres_path = tempfile.mkdtemp(prefix='astron-', suffix='.postgresql')
    postgresd = None
    output = None
    try:
        subprocess.run(
            [initdb, '-D', postgres_path, '--auth-local=trust', '--auth-host=trust'],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with open(os.path.join(postgres_path, 'postgresql.conf'), 'a') as config:
            # Keep the readiness message stable regardless of the runner locale.
            config.write("\nunix_socket_directories = '/tmp'\nlc_messages = 'C'\n")

        postgresd = subprocess.Popen(
            [postgres, '-D', postgres_path, '-h', POSTGRES_HOST, '-p', POSTGRES_PORT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
        )
        output = ProcessOutput(postgresd)

        _wait_for_postgres(output)
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
        if output is not None:
            output.join()
        details = output.tail() if output is not None else ''
        if details:
            error.args = ('%s\n%s' % (error, details),)
        shutil.rmtree(postgres_path, ignore_errors=True)
        raise

    unittest.postgres_path = postgres_path
    unittest.postgresd = postgresd
    unittest.postgres_output = output


def teardown_postgres(unittest):
    postgresd = getattr(unittest, 'postgresd', None)
    if postgresd is not None and postgresd.poll() is None:
        postgresd.terminate()
        try:
            postgresd.wait(timeout=10)
        except subprocess.TimeoutExpired:
            postgresd.kill()
            postgresd.wait()

    output = getattr(unittest, 'postgres_output', None)
    if output is not None:
        output.join()
        if postgresd.stdout is not None:
            postgresd.stdout.close()

    postgres_path = getattr(unittest, 'postgres_path', None)
    if postgres_path is not None:
        shutil.rmtree(postgres_path, ignore_errors=True)
