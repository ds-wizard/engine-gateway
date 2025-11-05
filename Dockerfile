FROM python:3.14-alpine

WORKDIR /app

ENV PATH="/app/bin:${PATH}"

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY . /app

RUN pip install .

CMD ["uvicorn", "engine_gateway:create_app", "--host", "0.0.0.0", "--port", "80", "--proxy-headers"]
