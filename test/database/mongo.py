import os
import shutil
import socket
import subprocess
import tempfile
import uuid

from common.process_output import ProcessOutput


MONGO_HOST = '127.0.0.1'
MONGO_PORT = int(os.environ.get('ASTRON_MONGO_TEST_PORT', '57024'))
# External MongoDB services can preserve their data between local/Compose test
# runs. Give each Python test process its own database, matching the clean
# temporary dbpath used when the tests launch mongod themselves.
MONGO_URI = 'mongodb://%s:%d/astron_test_%s' % (
    MONGO_HOST, MONGO_PORT, uuid.uuid4().hex
)
MONGO_INVALID_URI = 'baddb://%s:%d/test' % (MONGO_HOST, MONGO_PORT)
MONGO_STARTUP_TIMEOUT = 60


def _wait_for_mongo(mongod, output):
    if output is None:
        # CI-managed MongoDB services have their own health checks. Probe once
        # and fail with the endpoint in the message if the service is unhealthy.
        try:
            with socket.create_connection((MONGO_HOST, MONGO_PORT), timeout=5):
                return
        except OSError as error:
            raise RuntimeError(
                'External MongoDB at %s:%d is not ready: %s' %
                (MONGO_HOST, MONGO_PORT, error)
            )

    output.wait_for_any(
        ('waiting for connections',), MONGO_STARTUP_TIMEOUT, 'MongoDB'
    )
    with socket.create_connection((MONGO_HOST, MONGO_PORT), timeout=5):
        pass


def setup_mongo(unittest):
    external = os.environ.get('ASTRON_MONGO_TEST_EXTERNAL', '').lower() in ('1', 'true', 'yes')
    mongo_path = None
    mongod = None
    output = None

    if not external:
        mongo_path = tempfile.mkdtemp(prefix='astron-', suffix='.mongodb')
        mongod = subprocess.Popen(
            [
                'mongod',
                '--noauth',
                '--bind_ip', MONGO_HOST,
                '--port', str(MONGO_PORT),
                '--dbpath', mongo_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
        )
        output = ProcessOutput(mongod)

    try:
        _wait_for_mongo(mongod, output)
    except Exception as error:
        if mongod is not None and mongod.poll() is None:
            mongod.terminate()
            mongod.wait()
        if output is not None:
            output.join()
        if mongo_path is not None:
            details = output.tail() if output is not None else ''
            if details:
                error.args = ('%s\n%s' % (error, details),)
            shutil.rmtree(mongo_path, ignore_errors=True)
        raise

    unittest.mongo_path = mongo_path
    unittest.mongod = mongod
    unittest.mongo_output = output


def teardown_mongo(unittest):
    mongod = getattr(unittest, 'mongod', None)
    if mongod is not None and mongod.poll() is None:
        mongod.terminate()
        try:
            mongod.wait(timeout=10)
        except subprocess.TimeoutExpired:
            mongod.kill()
            mongod.wait()

    output = getattr(unittest, 'mongo_output', None)
    if output is not None:
        output.join()
        if mongod.stdout is not None:
            mongod.stdout.close()

    mongo_path = getattr(unittest, 'mongo_path', None)
    if mongo_path is not None:
        shutil.rmtree(mongo_path, ignore_errors=True)

    external = os.environ.get('ASTRON_MONGO_TEST_EXTERNAL', '').lower() in ('1', 'true', 'yes')
    if external:
        cleanup_executable = os.environ.get('ASTRON_MONGO_TEST_CLEANUP')
        if not cleanup_executable:
            raise RuntimeError(
                'ASTRON_MONGO_TEST_CLEANUP must name the MongoDB test cleanup executable'
            )
        subprocess.run([cleanup_executable, MONGO_URI], check=True, timeout=30)
