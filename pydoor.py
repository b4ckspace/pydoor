import asyncio

from quart import Quart


app = Quart(__name__)


@app.route("/operate")
def operate():
    return "Hello, world"


def main():
    loop = asyncio.get_event_loop()
    app.run(loop=loop)

    loop.run_forever()


if __name__ == "__main__":
    main()
