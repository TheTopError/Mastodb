import asyncio

from fetch_time_stats import FetchTimeStats
from mastodb import MastodonDB


def main():
    masto_db = MastodonDB()
    masto_db.mongo_handler.drop_all_collections()

    #stats = FetchTimeStats(masto_db.get_times())
    #stats.print_average()

    asyncio.run(masto_db.fetch_instances())
    asyncio.run(masto_db.fetch_posts())


if __name__ == '__main__':
    main()
