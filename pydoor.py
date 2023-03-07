import logging

from doorapp import get_door_app_environ
from authentication import get_authenticator_environ
from flask import Flask, redirect, request

logger = logging.getLogger(__name__)
app = Flask(__name__)
door_app = get_door_app_environ(start=True)
authenticator = get_authenticator_environ()


@app.route('/operate', methods=['GET', 'POST'])
def operate():
    if request.method == 'GET':
        return redirect('/')

    uid = request.form.get('uid', '')
    password = request.form.get('password', '')
    if not authenticator.check_credentials(uid, password):
        return redirect("/unauthorized.html")

    action = request.form.get('type', '').lower()
    if action == 'open':
        door_app.door_driver.unlock(uid)
        return redirect('/opened.html')
    elif action == 'close':
        door_app.door_driver.lock(uid)
        return redirect('/closed.html')


def main():
    app.run()


if __name__ == '__main__':
    main()
