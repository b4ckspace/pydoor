import base64
import hashlib
import hmac
import logging
import os
import re
import ssl

from ldap3 import Tls, Server, Connection
from ldap3.core.exceptions import LDAPException


logger = logging.getLogger(__name__)


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


def get_authenticator_environ():
    return LdapAuthenticator(
        os.environ.get('PYDOOR_LDAP_HOST', 'ldap://10.1.20.13:389'),
        os.environ.get('PYDOOR_LDAP_DN', 'cn=reader,ou=ldapuser,dc=backspace'),
        os.environ.get('PYDOOR_LDAP_PASSWORD', ''),
        os.environ.get('PYDOOR_LDAP_SEARCH', 'ou=member,dc=backspace')
    )
