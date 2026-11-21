FROM python:3.13-slim
WORKDIR /chatbot

COPY ./requirements.txt ./
RUN pip install --disable-pip-version-check --no-cache-dir -r requirements.txt

COPY src .

CMD ["python", "-m", "bot"]
