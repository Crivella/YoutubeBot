FROM python:3.12.9-slim-bullseye

RUN apt-get update && apt-get install \
    ffmpeg \
    -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /src

RUN pip install --upgrade pip

COPY req.txt /src

RUN pip install -r /src/req.txt

COPY concheddu_bot /src/concheddu_bot
COPY README.md /src
COPY LICENSE.txt /src
COPY pyproject.toml /src

RUN pip install /src[postgres,mysql]

RUN mkdir -p /bot

COPY start_bot.py /bot

ENV \
    BOT_TOKEN="" \
    BOT_PREFIX=. \
    BOT_FFMPEG_OPTIONS="" \
    BOT_AUDIO_DIR=/bot/dl \
    BOT_MAX_DURATION=420 \
    BOT_COLOR=ff0000 \
    BOT_YTDL_FORMAT=worstaudio

WORKDIR /bot

CMD ["python", "./start_bot.py"]
