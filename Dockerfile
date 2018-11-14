FROM python:3-alpine
COPY . .
RUN apk update
RUN apk add --virtual build-dependencies && apk add bash libc-dev && apk add gcc
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install python-Levenshtein
RUN echo "python ParamPP.py \$@" > init.sh
ENTRYPOINT ["/bin/sh","./init.sh"]
