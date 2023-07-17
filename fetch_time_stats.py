from typing import TypedDict


class FetchTimeStats:
    def __init__(self,
                 stats: list[TypedDict("FetchData", {"domain": str, "fetch_time": float, "toot_count": int})]):
        self.stats = stats

    def print_average(self):
        for stat in self.stats:
            if stat['toot_count'] == 0 or stat['fetch_time'] == 0: continue
            print("Average fetch time:",
                  str(round(stat['fetch_time'] / (stat['toot_count'] / 40), 5)).ljust(8, '0'), "on", stat['domain'])
