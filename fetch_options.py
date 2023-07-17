from __future__ import annotations
from abc import abstractmethod, ABC
from utils import get_json
from html.parser import HTMLParser


class Filter(ABC):

    @abstractmethod
    def filter(self, elements: list) -> list:
        """
        Returns all given elements that pass the filters.
        :param list elements: List of elements that were fetched.
        :return: List of elements that pass the filters.
        """
        pass

    @abstractmethod
    def params(self) -> dict:
        """
        Returns a dict for the fetch based on the filters.
        :return: Dict for the fetch based on the filters.
        """
        pass


class TootFilter(Filter):
    """
    Gives several filter options for toot fetch. To change options, edit ./search/toot_filter.json.
    """

    def __init__(self, toot_filter_link: str = "search/toot_filter.json"):
        """
       :param str toot_filter_link: Location of json-file in which the filtering options are set.
       """
        default_toot_filter = {
            "has_media": None,
            "has_image": None,
            "has_video": None,
            "substring": None,
            "languages": None,
        }
        toot_filter = get_json(toot_filter_link, default_toot_filter)
        self.substring = toot_filter["substring"]
        self.languages = toot_filter["languages"]
        self.has_image = toot_filter["has_image"]
        self.has_video = toot_filter["has_video"]
        self.has_media = toot_filter["has_media"]

        if self.has_video or self.has_image:
            self.has_media = True

    def filter(self, toots: list) -> list:
        result = []
        for toot in toots:

            # TODO: Add filter for sensitive

            if toot["language"] is None:
                continue

            if self.substring and self.substring not in toot["content"]:
                continue
            if self.languages and toot["language"] not in self.languages:
                continue
            if self.has_image is not None:
                image_in_toots = "image" in [media["type"] for media in toot["media_attachments"]]
                if self.has_image != image_in_toots:
                    continue
            if self.has_video is not None:
                video_in_toots = "video" in [media["type"] for media in toot["media_attachments"]]
                if self.has_video != video_in_toots:
                    continue
            result.append(toot)

        return result

    def params(self) -> dict:
        params = {"local": "true"}  # Do not change, may lead to duplicates.
        params |= {"limit": 40}
        if self.has_media is not None:
            params |= {"only_media": "true" if self.has_media else "false"}

        return params


class TootAttributes:
    """
       Handles the addition of toot attributes. To change which ones will be saved, edit ./search/toot_attributes.json.
    """
    class TootHTMLParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.output = ""

        def handle_starttag(self, tag, attrs):
            if tag in ["br"]:
                self.output += "\n"

        def handle_endtag(self, tag):
            if tag in ["p"]:
                self.output += "\n"

        def handle_data(self, data):
            self.output += data

        def parse_toot(self, string):
            self.output = ""
            self.feed(string)
            return self.output

    def __init__(self, toot_attributes_link: str = "search/toot_attributes.json"):
        """
        :param str toot_attributes_link: Location of json-file in which all attributes that should be added are true.
        """
        self.toot_html_parser = self.TootHTMLParser()
        default_toot_attributes = {
            "date": False,
            "content": True,
            "html_parsed_content": False,
            "language": False,
            "url": True,
            "uid": False,
            "sensitive": False,
            "favourites_count": False,
            "tags": False,
            "media": False
        }
        toot_attr = get_json(toot_attributes_link, default_toot_attributes)
        self.steps = []
        if toot_attr["url"]: self.steps.append(lambda toot: {"url": toot["url"]})
        if toot_attr["favourites_count"]: self.steps.append(lambda toot: {"favourites_count": toot["favourites_count"]})
        if toot_attr["sensitive"]: self.steps.append(lambda toot: {"sensitive": toot["sensitive"]})
        if toot_attr["date"]: self.steps.append(lambda toot: {"date": toot["created_at"]})
        if toot_attr["language"]: self.steps.append(lambda toot: {"language": toot["language"]})
        if toot_attr["uid"]: self.steps.append(lambda toot: {"uID": toot["account"]["id"]})
        if toot_attr["tags"]: self.steps.append(lambda toot: {"tags": [tag["name"] for tag in toot["tags"]]})
        if toot_attr["media"]:
            self.steps.append(lambda toot: {"media": [{"url": media["url"]} for media in toot["media_attachments"]]})

        if toot_attr["html_parsed_content"]: toot_attr["content"] = True
        if toot_attr["content"] and toot_attr["html_parsed_content"]:
            self.steps.append(lambda toot: {"content": self.toot_html_parser.parse_toot(toot["content"])})
        if toot_attr["content"] and not toot_attr["html_parsed_content"]:
            self.steps.append(lambda toot: {"content": toot["content"]})

    def create_toot_doc(self, toot: dict) -> dict:
        """
        Creates a dict from a fetched toot which is compatible to the database structure.
        :param dict toot: Fetched toot.
        :return dict: Dictionary with toot data which is compatible to the database structure.
        """

        if type(toot["id"]) != str:
            print("id of instance does not conform to mastodon rules.", toot)
            return dict()

        doc = {"_id": toot["id"]}
        for step in self.steps:
            try:
                doc |= step(toot)
            except KeyError:
                print("Toot does not contain an attribute:", toot)
                return dict()
        return doc



class InstanceFilter(Filter, ABC):
    """
    Gives several options for the instance search.
    """
    def __init__(self, instance_filter_link: str = "search/instance_filter.json"):
        default_instance_filter = {
            "amount_of_instances": 100,
            "min_users": 800,
            "min_active_users": 20,
            "amount_statuses": 10,
            "languages": None,
            "include_closed": False,
            "min_obs_score": None
        }
        instance_filter = get_json(instance_filter_link, default_instance_filter)
        self.amount_of_instances = instance_filter["amount_of_instances"]
        self.min_users = instance_filter["min_users"]
        self.min_active_users = instance_filter["min_active_users"]
        self.languages = instance_filter["languages"]
        self.include_closed = instance_filter["include_closed"]
        self.min_obs_score = instance_filter["min_obs_score"]
        self.amount_statuses = instance_filter["amount_statuses"]

    def filter(self, instances: list) -> list:
        result = []
        for instance in instances:
            if self.languages and (instance["info"]["languages"] is None or set(instance["info"]["languages"]).isdisjoint(self.languages)):
                continue
            if self.min_obs_score is not None and instance["obs_score"] < self.min_obs_score:
                continue
            if self.amount_statuses is not None and int(instance["statuses"]) < self.amount_statuses:
                continue

            result.append(instance)

        if len(result) == 0: print("No results passed the filters. Fetch more instances or change filters.")
        return result

    def params(self) -> dict:
        params = {"include_dead": "false"}
        if self.amount_of_instances is not None:
            params |= {"count": self.amount_of_instances}
        if self.min_users is not None:
            params |= {"min_users": self.min_users}
        if self.min_active_users is not None:
            params |= {"min_active_users": self.min_active_users}
        if self.include_closed is not None:
            params |= {"include_closed": "true" if self.include_closed else "false"}
        return params
