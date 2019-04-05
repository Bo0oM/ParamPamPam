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
from fuzzywuzzy import fuzz
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
        Конструктор ParamFinder
        :param url: URL
        :param method: тип запроса (GET, POST, PUT)
        :param cookie: строка с куками
        :param content_type: тип содержимого
        :param useragent: ну логично же, что это
        :param default_value: значение для параметра по умолчанию
        :param timeout: таймаут запросов
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
        Настраивает параметр для запроса в зависимости от типа запроса и
        типа содержимого
        :return:
        """
        # для POST/PUT и не urlencoded помещаем данные в тело запроса,
        # в противном случае - query string
        if (self.method in {'post', 'put'}
                and self.content_type != URLENCODED_CONTENT_TYPE):
            self.arg_param = 'data'
        else:
            self.arg_param = 'params'

    def _estimate_data_size(self, buf_size):
        """
        Вычисляет макс. допустимый объем данных для отправки
        :param buf_size: начальное значение
        :return: макс. объем (в байтах)
        """
        if self.arg_param == 'params':
            # Остаточный размер URI =
            #   размер буфера -
            #   длина базового +
            #   "мусорная" длина (не учитывается сервером) -
            #   3 (доп. символа)

            fullurl = urlparse(self.url)
            trash_len = len(fullurl.scheme+'://'+fullurl.netloc)
            remained_len = buf_size - len(self.url) + trash_len - 3
        else:
            # Остаточный размер данных = размер буфера - 2 (доп. символа)
            remained_len = buf_size - 2

        data = 'a' * remained_len
        try:
            dummy_response = request(url=self.url, allow_redirects=False, verify=SSLVERIFY, **self._wrap_params({data: 1}))
        except RequestException as e:
            print( e )
        #print (dummy_response.status_code)
        if dummy_response.status_code in {ENTITY_TOO_LARGE, URI_TOO_LARGE}:
            return self._estimate_data_size(buf_size // 2)

        # Не учитываем два доп. символа в итоге
        return remained_len + 2

    def _choose_metrics(self) -> list:
        """
        Выбирает метрики, подходящие для сравнения страниц между собой.
        :return: Список метрик (функторов)
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
            raise ValueError('Отсутствуют подходящие метрики '
                             'для сравнения страниц')

        return metrics

    def is_same(self, r1: Response, r2: Response) -> bool:
        """
        Сравнивает две страницы между собой, используя метрики
        :param r1: Response
        :param r2: Response
        :return: True, если страницы идентичны.
        """
        return all(metric(r1, r2) for metric in self._metrics)

    def _param_gen(self, q_params: list) -> Generator[dict, None, None]:
        """
        Создает генератор порций параметров на проверку-поиск
        :param q_params: общий список параметров
        :return: {параметр: значение, }
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
            # объем данных = объем всех (закодированных) параметров
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
        Сравнивает расстояние Левенштейна между двумя страницами
        :param r1: Response
        :param r2: Response
        :return: True, если расстояния равны.
        """
        return fuzz.ratio(r1.text, r2.text) == 100

    @staticmethod
    def _content_length_check(r1: Response, r2: Response) -> bool:
        """
        Сравнивает размеры двух страниц
        :param r1: Response
        :param r2: Response
        :return: True, если размеры идентичны.
        """
        #if (.verbose>0):
        #    print ('Origin Content-Length header: %s' % r1.headers.get('Content-Length', 0))
        #    print ('New Content-Length header: %s ' % r2.headers.get('Content-Length', 0))

        return r1.headers.get('Content-Length', 0) == r2.headers.get('Content-Length', 0) and len(r1.content) == len(r2.content)

    @staticmethod
    def _dom_check(r1: Response, r2: Response) -> bool:
        """
        Сравнивает количество элементов DOM дерева
        :param r1: Response
        :param r2: Response
        :return: True, если размеры идентичны.
        """
        #print (len(BeautifulSoup(r1.text, 'lxml').find_all()))
        #print (len(BeautifulSoup(r2.text, 'lxml').find_all()))

        #print (len(BeautifulSoup(r1.text, 'html5lib').find_all()))
        #print (len(BeautifulSoup(r2.text, 'html5lib').find_all()))

        return len(BeautifulSoup(r1.text, 'html5lib').find_all(True)) == len(BeautifulSoup(r2.text, 'html5lib').find_all(True))


    async def find_params(self, q_params: list) -> list:
        """
        Асинхронными запросами находит параметры, которые влияют на
        отображение страницы
        :param q_params: список названий параметров, среди которых необходимо
        выполнить поиск
        :return: список параметров, которые влияют на отображение страницы
        """

        # поиск тегов, которые содержат атрибут name
        if (PARSE_HTML):
            q_params.extend(parse_html(self._orig_response.text))

        # поиск и обработка javascript
        if (PARSE_JS):
            q_params.extend(get_js(self._orig_response.text, self.url))


        # На всякий случай, оставляем только уникальные параметры
        q_params = list(set(q_params))
        print ('Common count of have checked params: {}'.format(str(len(q_params))))
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
        Рекурсивно (методом дихотомии) находит параметры, которые влияют на
        отображение страницы
        :param params: dict({param_name: param_value})
        :return: список параметров, которые влияют на отображение страницы
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
        Заворачивает параметры для request в словарь
        :param params: dict({param_name: param_value})
        :return: словарь параметров для request
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
    # Ты сюда не смотри! Ты туда смотри!
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
        pass # блэт, это что, не js?
    return temp_params




if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-u', '--url', type=str, default='',
                        help='URL', required=True)

    parser.add_argument('-m', '--method', type=str,
                        default='GET', help='Тип запроса')

    parser.add_argument('-c', '--cookie', type=str, default='', help='Cookie')

    parser.add_argument('-ua', '--user-agent', type=str, default=USERAGENT, help='User-Agent')

    parser.add_argument('-d', '--default', type=str,
                        default=1, help='Значение параметров по умолчанию')

    parser.add_argument('-ct', '--content-type', type=str,
                        default='', help='Content-type')

    parser.add_argument('-f', '--filename', type=str, default='params.txt',
                        help='Имя файла со списком параметров')

    parser.add_argument('-t', '--timeout', type=int, default=1000,
                        help='Таймаут между запросами')

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
    
    print ('{}I\'ve found {} new real parametrs in follow request{}'.format(OKGREEN,len(finish),ENDC))
    link = args.url
    for param in finish:
        link+='&'+param+'='+str(args.default)

    print (OKGREEN + link + ENDC)

    #print(**self._wrap_params(finish))
