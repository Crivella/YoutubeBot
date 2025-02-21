FROM python:3.12.9-slim-bullseye

RUN apt-get update && apt-get install \
    ffmpeg \
    -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /src

COPY pyproject.toml /src
COPY concheddu_bot /src/concheddu_bot
COPY README.md /src
COPY LICENSE.txt /src

RUN pip install /src

RUN mkdir -p /bot

COPY start_bot.py /bot

ENV \
    BOT_TOKEN="" \
    BOT_PREFIX=. \
    BOT_FFMPEG_OPTIONS="" \
    BOT_AUDIO_DIR=/bot/dl \
    BOT_MAX_DURATION=720 \
    BOT_COLOR=ff0000 \
    BOT_YTDL_FORMAT=worstaudio

WORKDIR /bot

CMD ["python ./start_bot.py"]
