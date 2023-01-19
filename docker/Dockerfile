FROM python:3.9-alpine

RUN adduser --home /opt/pydoor --disabled-password pydoor

WORKDIR /opt/pydoor

COPY . ./
RUN pip install --no-cache-dir -r requirements.txt

USER pydoor

EXPOSE 8195

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=pydoor.py
ENV FLASK_DEBUG=1

#CMD ["flask", "run", "--host=0.0.0.0", "--port=8195"]
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:8195", "--access-logfile", "-", "--error-logfile", "-", "pydoor:app"]
