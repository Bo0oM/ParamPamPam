# ParamPamPam

This tool for brute discover GET and POST parameters.

**Installation**


Install [Docker](https://docs.docker.com/install/)

```
git clone https://github.com/Bo0oM/ParamPamPam.git
cd ParamPamPam
docker build -t parampp .
echo -e '#!'"/bin/bash\ndocker run -ti --rm parampp \$@" > /usr/local/bin/parampp
```

**Usage**
```
parampp -u "https://vk.com/login"
```

**TODO**
 * ADD json type
 * ADD multipart content-type
 * Fix errors
