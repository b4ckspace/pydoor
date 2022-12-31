import base64
import hashlib
import hmac
import logging
import os
import re
import ssl

from ldap3 import Tls, Server, Connection
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars


logger = logging.getLogger(__name__)


class LdapAuthenticator:
    HASH_ALGOS = {
        'md5': hashlib.md5,
        'sha': hashlib.sha1,
        'sha256': hashlib.sha256,
        'sha384': hashlib.sha384,
        'sha512': hashlib.sha512
    }

    def __init__(self, ldap_host, ldap_dn, ldap_password, ldap_search,
                 ldap_filter, ldap_password_attribute):
        self._ldap_host = ldap_host
        self._ldap_dn = ldap_dn
        self._ldap_password = ldap_password
        self._ldap_search = ldap_search
        self._ldap_filter = ldap_filter
        self._ldap_password_attribute = ldap_password_attribute

    def check_credentials(self, username, password):
        try:
            return self._check_credentials_internal(username, password)
        except LDAPException as e:
            logger.warning(f'Unexpected LDAP error: {e}')
        return False

    def _check_credentials_internal(self, username, password):
        tls_config = Tls(validate=ssl.CERT_NONE)
        server = Server(self._ldap_host, tls=tls_config)
        with Connection(server, self._ldap_dn, self._ldap_password) as conn:
            conn.start_tls()
            conn.bind()
            username_escaped = escape_filter_chars(username, 'utf-8')
            result = conn.search(
                self._ldap_search,
                self._ldap_filter.format(username=username_escaped),
                attributes=[self._ldap_password_attribute]
            )
            if not result:
                return False
            entry = conn.entries[0]
            door_password = getattr(entry, self._ldap_password_attribute)
            if not door_password:
                return False
            door_password_hash = str(door_password)
        return self._check_password_hash(password, door_password_hash)

    def _check_password_hash(self, password, password_hash):
        algo_options = '|'.join(self.HASH_ALGOS.keys())
        match = re.search(r'^{s?(' + algo_options + ')}', password_hash, re.IGNORECASE)
        if match is None:
            logger.warning('Invalid door password: Must start with {HASHALGO}')
            return False
        hash_class = self.HASH_ALGOS[match.group(1).lower()]
        password_hash = password_hash.removeprefix(match.group(0))
        try:
            password_hash_bytes = base64.b64decode(password_hash)
        except ValueError:
            logger.warning('Invalid base64 in door password attribute')
            return False
        hash_raw = password_hash_bytes[:hash_class.digest_size]
        salt_raw = password_hash_bytes[hash_class.digest_size:]
        user_hash = hash_class(password.encode('utf-8') + salt_raw).digest()
        return hmac.compare_digest(user_hash, hash_raw)


def get_authenticator_environ():
    return LdapAuthenticator(
        os.environ.get('PYDOOR_LDAP_HOST', 'ldap://10.1.20.13:389'),
        os.environ.get('PYDOOR_LDAP_DN', 'cn=reader,ou=ldapuser,dc=backspace'),
        os.environ.get('PYDOOR_LDAP_PASSWORD', ''),
        os.environ.get('PYDOOR_LDAP_SEARCH', 'ou=member,dc=backspace'),
        os.environ.get('PYDOOR_LDAP_FILTER', '(&(objectClass=backspaceMember)(serviceEnabled=door)(uid={username}))'),
        os.environ.get('PYDOOR_LDAP_PASSWORD_ATTRIBUTE', 'doorPassword')
    )
