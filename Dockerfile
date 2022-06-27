FROM python:3-alpine
COPY . .
RUN apk update && apk add build-base && \
    pip install --no-cache-dir -r requirements.txt && \
    echo -e '#!/bin/sh\npython -W ignore parampp.py $@' > ./init.sh && \
    chmod +x ./init.sh
ENTRYPOINT ["/init.sh"]
