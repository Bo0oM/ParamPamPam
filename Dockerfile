FROM python:3-alpine
COPY . .
RUN apk update && \
    apk add --virtual build-dependencies && \
    apk add bash libc-dev gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install python-Levenshtein && \
    echo "python ParamPP.py \$@" > /init.sh && \
    chmod +x /init.sh
ENTRYPOINT ["/init.sh"]
