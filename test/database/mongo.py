import os
import shutil
import socket
import subprocess
import tempfile
import time


MONGO_HOST = '127.0.0.1'
MONGO_PORT = 57024
MONGO_STARTUP_TIMEOUT = 60


def _wait_for_mongo(mongod):
    deadline = time.monotonic() + MONGO_STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if mongod is not None and mongod.poll() is not None:
            raise RuntimeError('mongod exited during startup')

        try:
            with socket.create_connection((MONGO_HOST, MONGO_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.25)

    raise RuntimeError('mongod did not start listening within 60 seconds')


def setup_mongo(unittest):
    external = os.environ.get('ASTRON_MONGO_TEST_EXTERNAL', '').lower() in ('1', 'true', 'yes')
    mongo_path = None
    mongod = None

    if not external:
        mongo_path = tempfile.mkdtemp(prefix='astron-', suffix='.mongodb')
        log_path = os.path.join(mongo_path, 'mongod.log')
        with open(log_path, 'w') as log_file:
            mongod = subprocess.Popen(
                [
                    'mongod',
                    '--noauth', '--quiet',
                    '--bind_ip', MONGO_HOST,
                    '--port', str(MONGO_PORT),
                    '--dbpath', mongo_path,
                ],
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

    try:
        _wait_for_mongo(mongod)
    except Exception as error:
        if mongod is not None and mongod.poll() is None:
            mongod.terminate()
            mongod.wait()
        if mongo_path is not None:
            try:
                with open(os.path.join(mongo_path, 'mongod.log'), 'r') as log_file:
                    details = log_file.read().strip()
                if details:
                    error.args = ('%s\n%s' % (error, details),)
            except OSError:
                pass
            shutil.rmtree(mongo_path, ignore_errors=True)
        raise

    unittest.mongo_path = mongo_path
    unittest.mongod = mongod


def teardown_mongo(unittest):
    mongod = getattr(unittest, 'mongod', None)
    if mongod is not None and mongod.poll() is None:
        mongod.terminate()
        try:
            mongod.wait(timeout=10)
        except subprocess.TimeoutExpired:
            mongod.kill()
            mongod.wait()

    mongo_path = getattr(unittest, 'mongo_path', None)
    if mongo_path is not None:
        shutil.rmtree(mongo_path, ignore_errors=True)
