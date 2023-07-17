from utils import get_json
from pymongo import MongoClient


# noinspection PyMethodMayBeStatic
class MongoHandler:
    def __init__(self, dbconfig_link: str):
        default_dbconfig = {
            "host": "",
            "port": -1,
            "database": "",
            "username": "",
            "password": ""
        }
        dbconfig = get_json(dbconfig_link, default_dbconfig)
        self.client = MongoClient(
            dbconfig["host"],
            dbconfig["port"],
            username=dbconfig["username"],
            password=dbconfig["password"],
            authSource=dbconfig["database"]
        )
        self.db = self.client[dbconfig["database"]]
        print("Connected to ", dbconfig["host"], ", ", dbconfig["port"],
              ". Using database ", dbconfig["database"], ".", sep="")

        if "instanceInfo" not in self.db.list_collection_names():
            self.db.create_collection("instanceInfo")



    def drop_all_collections(self):
        for collection in self.db.list_collection_names():
            self.db.drop_collection(collection)
