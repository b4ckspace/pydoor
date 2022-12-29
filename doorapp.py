import base64
import enum
import hashlib
import hmac
import logging
import os
import queue
import re
import signal
import ssl
import sys
import threading
import time
from datetime import datetime

from gpiozero import DigitalOutputDevice, Button
from ldap3 import Server, Connection, Tls
from ldap3.core.exceptions import LDAPException


logger = logging.getLogger(__name__)


class DoorApp:
    def __init__(self):
        self.authenticator = LdapAuthenticator(
            os.environ.get('PYDOOR_LDAP_HOST', 'ldap://10.1.20.13:389'),
            os.environ.get('PYDOOR_LDAP_DN', 'cn=reader,ou=ldapuser,dc=backspace'),
            os.environ.get('PYDOOR_LDAP_PASSWORD', ''),
            os.environ.get('PYDOOR_LDAP_SEARCH', 'ou=member,dc=backspace')
        )
        self.door_state = DoorState()
        self._door_state_thread = threading.Thread(target=self.door_state.run_forever)

    def start(self):
        self._door_state_thread.start()
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signo, sigframe):
        self.door_state.stop()
        self._door_state_thread.join()


class DoorOperations(enum.Enum):
    STOP = 1
    LOCK = 2
    UNLOCK = 3


class DoorCommand:
    def __init__(self, operation, args):
        self.operation = operation
        self.args = args

    def __repr__(self):
        return repr(self.__dict__)


class DoorState:
    def __init__(self):
        self._gpio1 = DigitalOutputDevice(23, active_high=False, initial_value=False)
        self._gpio2 = DigitalOutputDevice(24, active_high=False, initial_value=False)
        self._buzzer = DigitalOutputDevice(25, active_high=True, initial_value=False)
        self._command_queue = queue.SimpleQueue()

    def run_forever(self):
        is_running = True
        next_operation = None
        while is_running:
            command = self._command_queue.get()
            if command.operation == DoorOperations.STOP:
                is_running = False
            elif command.operation in (DoorOperations.LOCK, DoorOperations.UNLOCK):
                self._log_command(command)
                next_operation = command.operation
            else:
                logger.warning(f'PROGRAMMING ERROR: Invalid command: {command}')
            if self._command_queue.empty() and next_operation is not None:
                self._apply_operation(next_operation)
                next_operation = None

    def _apply_operation(self, next_state):
        if next_state == DoorOperations.UNLOCK:
            self._unlock_door()
        elif next_state == DoorOperations.LOCK:
            self._lock_door()

    def lock(self, who=None):
        self._command_queue.put(DoorCommand(DoorOperations.LOCK, {
            'who': who
        }))

    def unlock(self, who=None):
        self._command_queue.put(DoorCommand(DoorOperations.UNLOCK, {
            'who': who
        }))

    def stop(self):
        self._command_queue.put(DoorCommand(DoorOperations.STOP, {}))

    def _unlock_door(self):
        self._buzzer.on()
        self._gpio1.on()
        time.sleep(0.2)
        self._gpio1.off()
        time.sleep(5)
        self._buzzer.off()

    def _lock_door(self):
        self._gpio2.on()
        time.sleep(0.2)
        self._gpio2.off()

    def _log_command(self, command):
        who = command.args.get('who')
        now = datetime.utcnow()
        print(f'{now}: {command.operation.name} (user: {who})', file=sys.stderr)


class LdapAuthenticator:
    def __init__(self, ldap_host, ldap_dn, ldap_password, ldap_search):
        self._ldap_host = ldap_host
        self._ldap_dn = ldap_dn
        self._ldap_password = ldap_password
        self._ldap_search = ldap_search

    def check_credentials(self, username, password):
        try:
            return self._check_credentials_internal(username, password)
        except LDAPException as e:
            logger.warning(f'Unexpected LDAP error: {e}')
        return False

    def _check_credentials_internal(self, username, password):
        if not re.match('^[a-zA-Z0-9._-]+$', username):
            return False
        tls_config = Tls(validate=ssl.CERT_NONE)
        server = Server(self._ldap_host, tls=tls_config)
        with Connection(server, self._ldap_dn, self._ldap_password) as conn:
            conn.start_tls()
            conn.bind()
            result = conn.search(
                self._ldap_search,
                f'(&(objectClass=backspaceMember)(serviceEnabled=door)(uid={username}))',
                attributes=['uid', 'doorPassword']
            )
            if not result:
                return False
            entry = conn.entries[0]
            if not entry.doorPassword:
                return False
            door_password_hash = str(entry.doorPassword)
        return self._check_password_hash(password, door_password_hash)

    def _check_password_hash(self, password, password_hash):
        if not password_hash.startswith('{SSHA512}'):
            logger.warning('Invalid doorPassword: Must start with {SSHA512}.')
            return False
        password_hash = password_hash.removeprefix('{SSHA512}')
        try:
            password_hash_bytes = base64.b64decode(password_hash)
        except ValueError:
            logger.warning('Invalid base64 in doorPassword')
            return False
        sha512_raw = password_hash_bytes[:64]
        salt_raw = password_hash_bytes[64:]
        user_hash = hashlib.sha512(password.encode('utf-8') + salt_raw).digest()
        return hmac.compare_digest(user_hash, sha512_raw)