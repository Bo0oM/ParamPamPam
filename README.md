# ParamPamPam

This tool for brute discover GET and POST parameters.

Installation
---------
**With Docker**

Install [Docker](https://docs.docker.com/install/)

```
git clone https://github.com/Bo0oM/ParamPamPam.git
cd ParamPamPam
docker build -t parampp .
echo -e '#!'"/bin/bash\ndocker run -ti --rm parampp \$@" > /usr/local/bin/parampp

parampp -u "https://vk.com/login"
```

**If you are lazy**

Install Python3

```
git clone https://github.com/Bo0oM/ParamPamPam.git
cd ParamPamPam
pip3 install --no-cache-dir -r requirements.txt

python3 parampp.py -u "https://vk.com/login"
```


TODO
---------

 * ADD json type
 * ADD multipart content-type
 * Fix errors


Contributors 💪🏻
---------

* @eremenkonick
* @NooAn
