FROM python:3.12-alpine AS build
RUN apk add build-base
RUN python3 -m venv /build
WORKDIR /build
RUN /build/bin/pip wheel RPi.GPIO==0.7.1

FROM python:3.12-alpine

RUN adduser --home /opt/pydoor --disabled-password pydoor
# RUN mkdir /wheels

WORKDIR /opt/pydoor

COPY . ./
RUN --mount=type=bind,from=build,source=/build,target=/wheels pip install /wheels/*.whl
RUN pip install --no-cache-dir -r requirements.txt

USER pydoor

EXPOSE 8195

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=pydoor.py
ENV FLASK_DEBUG=1

#CMD ["flask", "run", "--host=0.0.0.0", "--port=8195"]
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:8195", "--access-logfile", "-", "--error-logfile", "-", "pydoor:app"]
