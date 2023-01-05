# pydoor

Automated door lock system based on Raspberry Pi

## Requirements

### Hardware

- Raspberry Pi (tested on Raspberry Pi 3)

### Operating System

- Raspberry Pi OS (formerly knows as Raspbian)

### Software

- Python 3 (uses system's Python 3 distribution)
- `python3-venv`
- `nginx`

For specific Python dependencies see `requirements.txt`.

### Installation

1. Clone this repository: `git clone https://github.com/b4ckspace/pydoor.git`
2. Create Python virtual environment, e.g.: `python3 -m venv venv`
3. Activate venv: `. venv/bin/activate`
4. In venv install dependencies: `pip install -r requirements.txt`
5. Copy systemd service file: `cp extras/systemd/pydoor.service /etc/systemd/system/`
6. Copy systemd service environment file: `cp extras/systemd/pydoor.env /etc/default/`
7. Adjust systemd serice enviroment file `/etc/default/pydoor.env`
8. Enable systemd service: `systemd enable pydoor.service`
9. Install and adjust nginx configuration: `cp extras/nginx/default /etc/nginx/conf.d/default`
10. Reload nginx: `systemd reload nginx.service` 
