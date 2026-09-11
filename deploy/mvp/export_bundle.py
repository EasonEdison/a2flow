"""Print one canonical reviewed demo bundle for the operator CLI."""

import argparse

from a2flow_asset_store.records import canonical
from activity_planning_demo.bundle import make_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("PRT", "ONLINE"), required=True)
    args = parser.parse_args()
    print(canonical(make_bundle(args.environment)).decode("utf-8"))


if __name__ == "__main__":
    main()
