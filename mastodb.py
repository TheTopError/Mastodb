import asyncio
import ssl

import aiohttp
import json
import time

import requests
import traceback

from typing import TypedDict

from aiohttp import ClientTimeout, TooManyRedirects, ServerDisconnectedError, ClientSession, ClientResponse, \
    ClientOSError, ClientConnectorError
from pymongo.errors import DuplicateKeyError, OperationFailure, BulkWriteError
from requests import Response

from fetch_options import TootFilter, InstanceFilter, TootAttributes
from mongo_handler import MongoHandler
from datetime import datetime as dt
from dateutil.parser import parse as date_parser
from asyncio import sleep, Task


# noinspection PyMethodMayBeStatic
class MastodonDB:

    def __init__(self,
                 dbconfig_link: str = "config/dbconfig.json",
                 toot_filter_link: str = "search/toot_filter.json",
                 toot_attributes_link: str = "search/toot_attributes.json",
                 instance_filter_link: str = "search/instance_filter.json",
                 ) -> None:
        self.mongo_handler = MongoHandler(dbconfig_link)

        self.toot_filter = TootFilter(toot_filter_link)
        self.toot_attributes = TootAttributes(toot_attributes_link)
        self.instance_filter = InstanceFilter(instance_filter_link)

        self.db = self.mongo_handler.db
        self.times = dict()
        self.cmp_toot_id = lambda toot: (len(toot["_id"]), toot["_id"])

    def _add_times(self) -> None:
        for domain, fetch_time in self.times.items():
            self.db["instanceData"].update_one({"_id": domain}, {"$inc": {"fetchTime": fetch_time}})
        print("Added all fetch durations.")

    def get_times(self) -> list[TypedDict("FetchData", {"domain": str, "fetch_time": float, "toot_count": int})]:
        result = list()
        instances_cursor = self.db["instanceData"].aggregate([
            {
                "$project": {
                    "_id": "$_id",
                    "fetchTime": "$fetchTime"
                }
            }
        ])
        for instanceDict in instances_cursor:
            result.append(
                {
                    "domain": instanceDict["_id"],
                    "fetch_time": instanceDict["fetchTime"],
                    "toot_count": self.db[instanceDict["_id"]].count_documents({})
                }
            )

        return result

    def _handle_res_status(self, domain, status: int, reason: str = "", print_message: bool = True) -> bool:
        """
        Prints info about the status and returns true if status is ok.
        :param str domain: Domain of the instance.
        :param int status: Status of response.
        :param str reason: Reason of response.
        :return: true if status is ok.
        """

        if status == 200:
            return True
        elif 500 > status > 399:
            if print_message: print("Client Error. HTTP-Status: ", status, ", ", reason, " ", domain, sep="")
        elif 600 > status > 499:
            if print_message: print("Server error. HTTP-Status: ", status, ", ", reason, " ", domain, sep="")
        else:
            msg = "Unexpected HTTP-status from " + domain + ": " + str(status) + " " + reason
            raise Exception(msg)
        return False

    async def _safe_async_get(self, url: str, error_value: any, time_limit: int = 3, get_json: bool = False):
        async with aiohttp.ClientSession() as session:
            try:
                res = await session.get(url, timeout=ClientTimeout(total=time_limit))
                status_ok = self._handle_res_status(url, res.status, res.reason)
                if not status_ok:
                    await session.close()
                    return error_value

                if get_json and res.content_type != "application/json":
                    print("Response is not in json-format, but ", res.content_type, ": ", url, sep="")
                    return error_value

                return await res.json() if get_json else res
            except Exception as e:
                await session.close()
                if isinstance(e, ssl.SSLCertVerificationError):
                    print("SSL certificate verification failed:", url)
                elif isinstance(e, ClientConnectorError):
                    print("Cannot connect to instance:", url)
                elif isinstance(e, TimeoutError):
                    print("Fetch took too long:", url)
                elif isinstance(e, ServerDisconnectedError):
                    print("Server disconnected:", url)
                elif isinstance(e, TooManyRedirects):
                    print("Too many redirects:", url)
                else:
                    print("Unknown Error:", url)
                    raise
                return error_value

    async def _fetch_first_toot(self, domain) -> dict:
        """
        Fetches the newest toot of an instance with the given domain and returns it.
        Returns dict() if an error occurs.
        """
        url = "https://" + domain + "/api/v1/timelines/public?limit=1"
        toot_json = await self._safe_async_get(url, dict(), 10, get_json=True)
        if len(toot_json) == 0:
            if toot_json != dict():
                print("Response has empty body:", domain)
            return dict()
        return toot_json[0]

    async def _fetch_instance_info(self, domain: str) -> dict:
        url = "https://" + domain + "/api/v1/instance"
        instance_info_json = await self._safe_async_get(url, dict(), get_json=True)
        return instance_info_json

    async def _fetch_domain_dict(self, domains: list[str], fetch_function) -> dict[str, dict]:
        tasks: dict[str, Task] = dict()
        async with asyncio.TaskGroup() as tg:
            for domain in domains:
                tasks[domain] = tg.create_task(fetch_function(domain))

        result: dict[str, dict] = dict()
        for domain, task in tasks.items():
            task_result = task.result()
            if task_result != dict():
                result[domain] = task_result
        return result

    async def add_instances(self, domains: list[str], instances: dict[str, dict] = None) -> None:
        """
       Fetches info about the instances with the given domains and stores them in the database together with one toot.
       :param list[str] domains: Domains of the mastodon instances. E.g. ['mastodon.social'].
       :param dict[str, dict] instances: Optional, dict[domain] with info of the instance if already available.
       :return None:
       """
        if "instanceData" in domains: domains.remove("instanceData")

        toot_dict = await self._fetch_domain_dict(domains, self._fetch_first_toot)
        if instances is None:
            instances = await self._fetch_domain_dict(domains, self._fetch_instance_info)

        # TODO: Do all inserts at the same time.
        with self.db.client.start_session() as session:
            for domain, toot in toot_dict.items():
                if domain not in instances: continue
                try:
                    self.db["instanceData"].insert_one({
                        "_id": domain,
                        "languages": instances[domain]["languages"],
                        "caughtUp": False,
                        "fetchTime": 0,
                    }, session=session)
                    doc = self.toot_attributes.create_toot_doc(toot)
                    if doc is dict(): continue
                    self.db[domain].insert_one(doc, session=session)
                    print("Created collection for instance:", domain)
                except DuplicateKeyError:
                    print("Did not create collection for instance, as it already exists.")

    def _get_instance_dict(self) -> dict:
        """
        Pulls necessary data of the instances from the given database.
            \n bool caught_up: True if the oldest post has already been fetched.
            \n str new_id: ID of the newest fetched toot of the instance.
            \n str old_id: ID of the oldest fetched toot of the instance.
            \n
        :return dict: The dictionary has the following structure: {domain: [caught_up, new_id, old_id]}
        """
        is_caught_up_dict = self.db["instanceData"].aggregate([
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$arrayToObject": [
                            [{
                                "k": "$_id",
                                "v": "$caughtUp"
                            }]
                        ]
                    }
                }
            }
        ])
        result = dict()
        for entry in is_caught_up_dict:
            instance, caught_up = list(entry.items())[0]
            try:
                new_old_id = self.db[instance].aggregate([
                    {
                        "$project": {
                            "_id": "$_id",
                            "idLength": {"$strLenCP": "$_id"}
                        }
                    },
                    {
                        "$sort": {
                            "idLength": -1,
                            "_id": -1
                        }
                    },
                    {
                        "$group": {
                            "_id": "null",
                            "new_id": {"$first": "$_id"},
                            "old_id": {"$last": "$_id"}
                        }
                    }
                ]).next()
                result[instance] = [caught_up, new_old_id["new_id"], new_old_id["old_id"]]
            except OperationFailure:
                print("Broken Instance:", instance)
                continue
        return result

    async def _handle_fetch_batch_status(self, domain, res) -> bool | None:
        if "x-ratelimit-remaining" not in res.headers: return False
        if res.status == 429:
            reset_timestamp = dt.timestamp(date_parser(res.headers["x-ratelimit-reset"]))
            delta = abs(reset_timestamp - dt.timestamp(dt.now()))
            print("Too many requests ", domain, " waiting for ", round(delta), "s.", sep="")
            await sleep(delta + 1)
            return None
        else:
            return self._handle_res_status(domain, res.status, res.reason)

    async def _get_batch(self, session: ClientSession, domain: str, params: dict) -> ClientResponse | None:
        try:
            return await session.get("https://" + domain + "/api/v1/timelines/public", params=params,
                                     timeout=ClientTimeout(total=10))
        except Exception as e:
            if isinstance(e, ClientOSError):
                print("ClientOSError occurred:", domain)
            elif isinstance(e, ClientConnectorError):
                print("Cannot connect to instance:", domain)
            elif isinstance(e, ssl.SSLCertVerificationError):
                print("SSL certificate verification failed:", domain)
            elif isinstance(e, TimeoutError):
                print("Fetch took too long:", domain)
            elif isinstance(e, ServerDisconnectedError):
                print("Server disconnected:", domain)
            elif isinstance(e, TooManyRedirects):
                print("Too many redirects:", domain)
            else:
                print("Unknown Error:", domain)
                raise
            return

    async def _fetch_batch(self, instance: tuple[str, tuple[bool, str, str]], session: ClientSession) -> None:
        """
        Fetches toots from all the instances in the database in an asynchronous fetch-loop.
        :param instance: Date of the instances for the fetch-loop: domain, (caught_up, new_id, old_id).
        :return:
        """
        # Possible Speedup: Extract as many posts as possible and only put in DB if waiting time starts.
        param_options = self.toot_filter.params()
        domain, (caught_up, new_id, old_id) = instance

        while True:
            params = param_options | ({"min_id": new_id} if caught_up else {"max_id": old_id})

            fetch_start = time.time()
            res = await self._get_batch(session, domain, params)
            fetch_time = time.time() - fetch_start

            if res is None: return
            status_ok = await self._handle_fetch_batch_status(domain, res)
            if status_ok is None: return
            if not status_ok: continue
            print("Remaining fetches: ", res.headers["x-ratelimit-remaining"], ", ", res.request_info.url, sep="")

            toots = []
            try:
                toots_data: list[dict] = await res.json()
            except asyncio.TimeoutError:
                print("Json not parsable: ", domain)
                continue
            for toot in self.toot_filter.filter(toots_data):
                if toot is dict(): return
                toots.append(self.toot_attributes.create_toot_doc(toot))
            if len(toots) == 0: continue

            try:
                self.db[domain].insert_many(toots)
            except BulkWriteError:
                print("Duplicate key error: ", domain)
                continue
            self.times[domain] = self.times.setdefault(domain, 0) + fetch_time  # Needs to be done after adding the toots.
            new_id = max(*toots, {"_id": new_id}, key=self.cmp_toot_id)["_id"]
            old_id = min(*toots, {"_id": old_id}, key=self.cmp_toot_id)["_id"]

            # We reached the newest post, we also have caught up with the oldest. No more posts to get.
            if len(toots_data) < 40 and caught_up: return
            # We caught up with the oldest post. Only posts newer than the newest post in DB will be fetched now.
            elif len(toots_data) < 40 and not caught_up:
                self.db["instanceData"].update_one({"_id": domain}, {"$set": {"caughtUp": True}})
                return

    async def fetch_posts(self) -> None:
        """
        Fetches toots from instances stored in the given database and stores them in it. Press CTRL+C to stop.
        :return None:
        """
        try:
            async with aiohttp.ClientSession() as session:
                x = [self._fetch_batch(entry, session) for entry in self._get_instance_dict().items()]
                print(len(x))
                await asyncio.gather(*x)
                raise SystemExit("Closed Program")
        except:
            self._add_times()
            traceback.print_exc()

    def _get_domains_and_instances(self, res: Response) -> tuple[list[str], dict[str, dict]]:
        domains = []
        instances = dict()
        for instance in self.instance_filter.filter(res.json()["instances"]):
            domains.append(instance["name"])
            instances[instance["name"]] = {
                "_id": instance["name"],
                "languages": instance["info"]["languages"],
                "caughtUp": False,
            }
        return domains, instances

    async def fetch_instances(self, api_token_link: str = "config/api_token.json") -> None:
        """
        Fetches instances from the instances.social API which are than added to the database.
        :param str api_token_link: API token which can be created on https://instances.social/api/token.
        :return None:
        """
        if api_token_link == "":
            print("An API token is needed. You can create one on https://instances.social/api/token.")
            return

        with open(api_token_link, "r") as dbconfig_file:
            api_token = json.load(dbconfig_file)["token"]

        headers = {"Authorization": "Bearer " + api_token}
        url = "https://instances.social/api/1.0/instances/list"
        res = requests.get(url, params=self.instance_filter.params(), headers=headers)

        reason = "Probably invalid Token. https://instances.social/api/token." if res.status_code == 400 else res.reason
        status_ok = self._handle_res_status(url, res.status_code, reason)
        if not status_ok: return

        domains, instances = self._get_domains_and_instances(res)
        await self.add_instances(domains, instances)
