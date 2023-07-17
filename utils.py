import os
import json


def get_json(link: str, defaultdict: dict) -> dict:
    if defaultdict is None:
        raise ValueError("defaultdict must not be None!")

    if not os.path.exists(link):
        with open(link, "x") as file:
            new_json_object = json.dumps(defaultdict)
            file.write(new_json_object)
    elif not os.path.isfile(link):
        raise IsADirectoryError("Given Path", link, "is not a file, but a directory.")

    with open(link, "r") as file:
        try:
            json_object: dict = json.load(file)
        except json.decoder.JSONDecodeError:
            print("-" * 60, "\n" * 2, "File with", link, "is not in json-format.", "\n" * 2, "-" * 60)
            raise

        if not defaultdict.keys() <= json_object.keys():
            raise ValueError("File with path", link, "doesn't have the needed attributes.\nDelete the file",
                             "and restart the program to create a file with the correct attributes.")
        return json_object
