# coding=utf-8

import argparse, asyncio, random, string, esprima
from concurrent.futures import ProcessPoolExecutor
from http.cookies import SimpleCookie
from itertools import islice
from bs4 import BeautifulSoup
from typing import Generator
from urllib.parse import urlencode, urlparse, urljoin
from requests import request, Response, RequestException

# pip install python-Levenshtein
from rapidfuzz import fuzz
#
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Тестовые параметры
PARSE_JS = True
PARSE_HTML = True
SSLVERIFY = False
#
USERAGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
URLENCODED_CONTENT_TYPE = 'application/x-www-form-urlencoded'
DEFAULT_URL_BUF_SIZE = 8192

ENTITY_TOO_LARGE = 413
URI_TOO_LARGE = 414
NUM_PROCESSES = 10
ENDC = '\033[0m'
OKGREEN ='\033[92m'
WARNING ='\033[93m'


def split_dict(d: dict) -> (dict, dict):
    """
    Разбивает словарь d пополам
    :param d: dict
    :return: dict, dict
    """
    n = len(d) // 2
    i = iter(d.items())

    d1 = dict(islice(i, n))
    d2 = dict(i)

    return d1, d2


class ParamFinder:

    def __init__(self, url, method, cookie='',
                 useragent=USERAGENT,
                 content_type=URLENCODED_CONTENT_TYPE,
                 default_value=1, timeout=10,
                 verbose=0, auth = ''):
        """
        ParamFinder constructor
        :param url: URL
        :param method: request type (GET, POST, PUT)
        :param cookie: cookie string
        :param content_type: content type
        :param useragent: you can guess what it is
        :param default_value: The value for the default
        :param timeout: request timeout
        """
        self.url = url
        self.req_params = {
            'method': method.lower(),
            'timeout': timeout
        }
        self.arg_param = 'params'

        self.useragent = useragent

        if cookie:
            self.cookie = cookie

        if self.method in {'post', 'put'}:
            self.content_type = content_type

        self.default_value = default_value

        self.verbose = verbose

        self.auth = auth

        self._orig_response = request(url=url, allow_redirects=False, verify=SSLVERIFY, **self.req_params)

        self.max_data_size = self._estimate_data_size(DEFAULT_URL_BUF_SIZE)
        self._metrics = self._choose_metrics()
        if (self.verbose>0):
            print ('Origin response; Code={} and lenght={}: and verbose = {}\n'.format(self._orig_response.status_code, len(self._orig_response.content), self.verbose))
            print ('Chosen metrics: {}\n'.format((self._metrics)))



    @property
    def timeout(self):
        return self.req_params.get('timeout')

    @timeout.setter
    def timeout(self, value):
        self.req_params['timeout'] = value

 
    @property
    def cookie(self):
        return self.req_params.get('cookies')


    @cookie.setter
    def cookie(self, value):
        self.req_params['cookies'] = {key:morsel.value for key, morsel in SimpleCookie(value).items()}


    @property
    def useragent(self):
        return self.req_params.get('headers', {}).get(
            'User-agent', USERAGENT
        )

    @useragent.setter
    def useragent(self, value):
        headers = self.req_params.setdefault('headers', {})
        headers['User-agent'] = value


    @property
    def content_type(self):
        return self.req_params.get('headers', {}).get(
            'Content-Type', URLENCODED_CONTENT_TYPE
        )

    @content_type.setter
    def content_type(self, value):
        headers = self.req_params.setdefault('headers', {})
        headers['Content-Type'] = value
        self._setup_arg_param()


    @property
    def method(self):
        return self.req_params.get('method')

    @method.setter
    def method(self, value):
        self.req_params['method'] = value.lower()
        self._setup_arg_param()   
  
    @property
    def auth(self):
        return self.req_params.get('headers',{}).get(
                'Autorization',''
        )
    
    @auth.setter
    def auth(self,value):
        headers = self.req_params.setdefault('headers', {})
        headers['Authorization']=value

    def _setup_arg_param(self):
        """
        Configures the parameter for the request depending on 
        the type of request and the type of content
        :return:
        """
        # for POST/PUT and not urlencoded put the data in the
        # body of the request, else - query string
        if (self.method in {'post', 'put'}
                and self.content_type != URLENCODED_CONTENT_TYPE):
            self.arg_param = 'data'
        else:
            self.arg_param = 'params'

    def _estimate_data_size(self, buf_size):
        """
        Calculates the maximum allowed amount of data to send
        :param buf_size: initial value
        :return: max volume (in bytes)
        """
        if self.arg_param == 'params':
            # Residual URI size
            # buffer size -
            # length of base +
            # "trash" length (not counted by the server) -
            # 3 (extra characters)

            fullurl = urlparse(self.url)
            trash_len = len(fullurl.scheme+'://'+fullurl.netloc)
            remained_len = buf_size - len(self.url) + trash_len - 3
        else:
            # Residual data size = buffer size - 2 (extra characters)
            remained_len = buf_size - 2

        data = 'a' * remained_len
        try:
            dummy_response = request(url=self.url, allow_redirects=False, verify=SSLVERIFY, **self._wrap_params({data: 1}))
        except RequestException as e:
            print( e )
        #print (dummy_response.status_code)
        if dummy_response.status_code in {ENTITY_TOO_LARGE, URI_TOO_LARGE}:
            return self._estimate_data_size(buf_size // 2)

        # Ignore the two extra characters 
        return remained_len + 2

    def _choose_metrics(self) -> list:
        """
        Selects metrics suitable for comparing pages against each other.
        :return: List of metrics (functors)
        """

        metrics = [self._content_length_check, self._lev_distance_check, self._dom_check]

        for k in [10, 15, 20]:
            not_param = ''.join(random.sample(string.ascii_letters, k=k))
            params = {not_param: self.default_value}
            response = request(url=self.url, allow_redirects=False, verify=SSLVERIFY, **self._wrap_params(params))
            if (self.verbose>0):
                print ('\nResponse from metrics {}'.format(response.content))
                print ('\nParams for metrics {}'.format(params))

            for metric in metrics[:]:
                if not metric(self._orig_response, response):
                    metrics.remove(metric)

        if not metrics:
            raise ValueError('There are no appropriate metrics '
                             'to compare pages')

        return metrics

    def is_same(self, r1: Response, r2: Response) -> bool:
        """
        Compares two pages with each other using metrics
        :param r1: Response
        :param r2: Response
        :return: True if the pages are identical.
        """
        return all(metric(r1, r2) for metric in self._metrics)

    def _param_gen(self, q_params: list) -> Generator[dict, None, None]:
        """
        Creates a generator of parameter portions to check-search
        :param q_params: generic parameter list
        :return: {parameter: value, }
        """
        def qs_line_len(param, value):
            return len(urlencode(((param, value),)))

        def body_data_len(param, value):
            return len('{}={}'.format(param, value))

        if self.arg_param == 'params':
            get_len = qs_line_len
        else:
            get_len = body_data_len

        params = {}
        data_size = 0

        while q_params:
            q_param = q_params.pop()
            n_line_len = get_len(q_param, self.default_value)
            # data volume = volume of all (encoded) parameters
            if data_size + n_line_len + len(params) - 1 > self.max_data_size:
                yield params.copy()
                params.clear()
                data_size = 0

            params[q_param] = self.default_value
            data_size += n_line_len

        yield params

    @staticmethod
    def _lev_distance_check(r1: Response, r2: Response) -> bool:
        """
        Compares the Levenshtein distance between two pages
        :param r1: Response
        :param r2: Response
        :return: True if the distances are equal.
        """
        return fuzz.ratio(r1.text, r2.text) == 100

    @staticmethod
    def _content_length_check(r1: Response, r2: Response) -> bool:
        """
        Compares the size of the two pages
        :param r1: Response
        :param r2: Response
        :return: True if the sizes are identical.
        """
        #if (.verbose>0):
        #    print ('Origin Content-Length header: %s' % r1.headers.get('Content-Length', 0))
        #    print ('New Content-Length header: %s ' % r2.headers.get('Content-Length', 0))

        return r1.headers.get('Content-Length', 0) == r2.headers.get('Content-Length', 0) and len(r1.content) == len(r2.content)

    @staticmethod
    def _dom_check(r1: Response, r2: Response) -> bool:
        """
        Compares the number of elements in the DOM tree
        :param r1: Response
        :param r2: Response
        :return: True if the sizes are identical.
        """
        #print (len(BeautifulSoup(r1.text, 'lxml').find_all()))
        #print (len(BeautifulSoup(r2.text, 'lxml').find_all()))

        #print (len(BeautifulSoup(r1.text, 'html5lib').find_all()))
        #print (len(BeautifulSoup(r2.text, 'html5lib').find_all()))

        return len(BeautifulSoup(r1.text, 'html5lib').find_all(True)) == len(BeautifulSoup(r2.text, 'html5lib').find_all(True))


    async def find_params(self, q_params: list) -> list:
        """
        Asynchronous queries find parameters that affect the display of the page
        :param q_params: a list of parameter names to search for
        :return: a list of parameters that affect the display of the page
        """

        # search for tags that contain the name attribute
        if (PARSE_HTML):
            q_params.extend(parse_html(self._orig_response.text))

        # javascript search and processing
        if (PARSE_JS):
            q_params.extend(get_js(self._orig_response.text, self.url))


        # Just in case, we leave only unique parameters
        q_params = list(set(q_params))
        try:
            with open('new_params.txt', 'w') as f:
                for p in q_params:
                    f.write("%s\n" % p)
                print("New params were saved in new_params.txt")
        except Exception as e:
            print( e )
        print ('Common count of have just checked params: {}'.format(str(len(q_params))))
        ###

        result = []
        with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor,
                    self._find_params,
                    params
                ) for params in self._param_gen(q_params)
            ]
            for res in await asyncio.gather(*futures):
                result.extend(res)

        return result

    def _find_params(self, params: dict) -> list:
        """
        Recursively (by dichotomy) finds parameters that affect the display of the page
        :params: dict({param_name: param_value})
        :return: list of parameters that affect the display of the page
        """
        
        response = request(url=self.url, allow_redirects=False, verify=SSLVERIFY, **self._wrap_params(params))
        if (self.verbose>0):
            print ('New request with params\n: {}'.format(response.url))
            print ("New response new: {}\n".format(str(response.content)))
            print ("This site is the same? Answer: {}\n\n".format(str(self.is_same(self._orig_response, response))))        
        if not self.is_same(self._orig_response, response):
            if len(params) == 1:
                return list(params.keys())

            left, right = split_dict(params)

            left_keys = self._find_params(left)
            right_keys = self._find_params(right)

            return left_keys + right_keys

        return []

    def _wrap_params(self, params: dict) -> dict:
        """
        Wraps the parameters for the request into a dictionary
        :params: dict({param_name: param_value})
        :return: parameter dictionary for request
        """
        return {**self.req_params, **{self.arg_param: params}}

#def merge_lists(q_params, templist):
#    for element in templist:
#      q_params.extend(element)
#    return q_params

def parse_html(response):
    print ('Parsing HTML')
    temp_params = []
    for tag in BeautifulSoup(response, 'html5lib').find_all(attrs={"name": True}):
                temp_params.append(tag.attrs.get('name'))
    print ('{}Found {} new params in html{}'.format(OKGREEN,len(temp_params), ENDC))
    #if len(temp_params) > 0:
    #    print (temp_params)
    return temp_params

def get_js(response, url):
    # There may be better ways to parse js, but for now this
    print ('Parsing JavaScript')
    js_params = []
    js=""
    for script in BeautifulSoup(response, 'html5lib').find_all('script'):
        if 'src' in script.attrs:
            if (urlparse(script.get('src')).netloc!=''):
                scheme = urlparse(url).scheme+':' if urlparse(script.get('src')).scheme=='' else ''
                js_params.extend(parse_js(request('get', scheme+script.get('src'), verify=SSLVERIFY).text))
            else:
                src=urljoin(url,script.get('src'))
                js_params.extend(parse_js(request('get', src, verify=SSLVERIFY).text))
        else:
            js_params.extend(parse_js(script.text))


    js_params = list(set(js_params))
    print ('{}Found {} new params in js {}\n'.format(OKGREEN,len(js_params),ENDC))
    #if len(js_params)>0:
    #    print (js_params)
    return js_params

def parse_js(text):
    temp_params = []
    try:
        jsparse = esprima.tokenize(text)
        for token in jsparse:
            if token.type == 'Identifier':
                temp_params.append(token.value)
    except:
        pass # oops, isn't that js?
    return temp_params




if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-u', '--url', type=str, default='',
                        help='URL', required=True)

    parser.add_argument('-m', '--method', type=str,
                        default='GET', help='Type of request')

    parser.add_argument('-c', '--cookie', type=str, default='', help='Cookie')

    parser.add_argument('-ua', '--user-agent', type=str, default=USERAGENT, help='User-Agent')

    parser.add_argument('-d', '--default', type=str,
                        default=1, help='Default parameter value')

    parser.add_argument('-ct', '--content-type', type=str,
                        default='', help='Content-type')

    parser.add_argument('-f', '--filename', type=str, default='params.txt',
                        help='File name with a list of parameters')

    parser.add_argument('-t', '--timeout', type=int, default=10,
                        help='Timeout between requests')

    parser.add_argument('-v','--verbose', type=int, default=0,help='Level of logs')

    parser.add_argument('-a', '--auth', type=str, default='',help='Authorization header')
    

    args = parser.parse_args()

    print ("Start up...")

    finder = ParamFinder(
        url=args.url,
        method=args.method,
        cookie=args.cookie,
        useragent=args.user_agent,
        content_type=args.content_type,
        default_value=args.default,
        timeout=args.timeout,
        verbose=args.verbose,
        auth=args.auth
    )

    with open(args.filename, 'r') as f:
        params = f.read().splitlines()

    loop = asyncio.get_event_loop()
    finish=(loop.run_until_complete(finder.find_params(params)))
    
    print ('{}I\'ve found {} new real parameters in follow request{}'.format(OKGREEN,len(finish),ENDC))
    link = args.url
    for param in finish:
        link+='&'+param+'='+str(args.default)

    print (OKGREEN + link + ENDC)

    #print(**self._wrap_params(finish))
