import os
import sys

from demo.replay import export
from store import Store

if __name__ == "__main__":
    investigation_id, scenario = sys.argv[1], sys.argv[2]
    print(export(Store(os.environ.get("FRAUDLENS_DB", "../fraudlens.db")), investigation_id, scenario))
