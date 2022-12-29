import logging

from doorapp import DoorApp
from flask import Flask, redirect, request

logger = logging.getLogger(__name__)
app = Flask(__name__)
door_app = DoorApp()
door_app.start()


@app.route('/operate', methods=['POST'])
def operate():
    uid = request.form.get('uid', '')
    password = request.form.get('password', '')
    if not door_app.authenticator.check_credentials(uid, password):
        return redirect("/unauthorized.html")

    action = request.form.get('type', '').lower()
    if action == 'open':
        door_app.door_state.unlock(uid)
        return redirect('/opened.html')
    elif action == 'close':
        door_app.door_state.lock(uid)
        return redirect('/closed.html')


def main():
    app.run()


if __name__ == '__main__':
    main()
