import asyncio
import base64
import binascii
import configparser
import hashlib
import hmac
import logging
import ssl
import re
from urllib.parse import parse_qs

from ldap3 import Server, Connection, Tls, ALL
from ldap3.core.exceptions import LDAPSocketOpenError, LDAPException
from flask import Flask, redirect, request


LDAP_HOST = 'ldap://10.1.20.13:389'
LDAP_USER_DN = 'ou=member,dc=backspace'
LDAP_ADMIN_DN = 'cn=reader,ou=ldapuser,dc=backspace'
LDAP_ADMIN_PASSWORD = ''


logger = logging.getLogger(__name__)
app = Flask(__name__)


def check_password(username, password):
    try:
        return _check_password_interal(username, password)
    except LDAPException as e:
        logger.warning(f'Unexpected LDAP error: {e}')
    return False


def _check_password_interal(username, password):
    if not re.match('^[a-zA-Z0-9._-]+$', username):
        return False
    tls_config = Tls(validate=ssl.CERT_NONE)
    server = Server(LDAP_HOST, tls=tls_config)
    with Connection(server, LDAP_ADMIN_DN, LDAP_ADMIN_PASSWORD) as conn:
        conn.start_tls()
        conn.bind()
        result = conn.search(
                LDAP_USER_DN,
                f'(&(objectClass=backspaceMember)(serviceEnabled=door)(uid={username}))',
                attributes=['uid', 'doorPassword']
        )
        if not result:
            return False
        entry = conn.entries[0]
        if not entry.doorPassword:
            return False
        door_password = str(entry.doorPassword)
        if not door_password.startswith('{SSHA512}'):
            logger.warning('Invalid doorPassword: Must start with {SSHA512}.')
            return False
        door_password = door_password.removeprefix('{SSHA512}')
        try:
            door_password_bytes = base64.b64decode(door_password)
        except ValueError:
            logger.warning('Invalid base64 in doorPassword')
            return False
        sha512_raw = door_password_bytes[:64]
        salt_raw = door_password_bytes[64:]
        user_hash = hashlib.sha512(password.encode('utf-8') + salt_raw).digest()
    return hmac.compare_digest(user_hash, sha512_raw)


@app.route("/operate", methods=["POST"])
def operate():
    if not check_password(request.form["uid"], request.form["password"]):
        return redirect("/unauthorized.html")

    if lower(request.form["type"]) == "open":
        return redirect("/opened.html")

    if lower(request.form["type"]) == "close":
        return redirect("/closed.html")


def main():
    config = configparser.ConfigParser()

    config.read("config.ini")
    config_dict = {}

    for section in config.sections():
        if "." in section:
            section_names = section.split(".")

            if section_names[0] not in config_dict:
                config_dict[section_names[0]] = {
                        section_names[1]: dict(config[section])
                }
            else:
                config_dict[section_names[0]][section_names[1]] = dict(config[section])
        else:
            config_dict[section] = dict(config[section])

    config = config_dict

    app.run()


if __name__ == '__main__':
    main()
