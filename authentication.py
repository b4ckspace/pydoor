import base64
import hashlib
import hmac
import logging
import os
import re


logger = logging.getLogger(__name__)


class ShadowFileAuthenticator:
    HASH_ALGOS = {
        'md5': hashlib.md5,
        'sha': hashlib.sha1,
        'sha256': hashlib.sha256,
        'sha384': hashlib.sha384,
        'sha512': hashlib.sha512
    }

    def __init__(self, shadow_file):
        if not os.path.exists(shadow_file):
            raise FileNotFoundError(f'File does not exist: {shadow_file}')

        if not os.access(shadow_file, os.R_OK):
            raise PermissionError (f'Cannot read shadow file: {shadow_file}')

        self._shadow_file = shadow_file

    def check_credentials(self, username, password):
        with open(self._shadow_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                user, _, password_hash = line.partition(':')

                if user == username:
                    return self._check_password_hash(password, password_hash)

        return False

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
        digest_size = hash_class().digest_size
        hash_raw = password_hash_bytes[:digest_size]
        salt_raw = password_hash_bytes[digest_size:]
        user_hash = hash_class(password.encode('utf-8') + salt_raw).digest()
        return hmac.compare_digest(user_hash, hash_raw)


def get_authenticator_environ():
    return ShadowFileAuthenticator(
        shadow_file=os.environ.get('PYDOOR_SHADOW_FILE', '/etc/pydoor/shadow')
    )
