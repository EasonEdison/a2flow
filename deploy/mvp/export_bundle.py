"""Print one canonical reviewed demo bundle for the operator CLI."""

import argparse

from a2flow_asset_store.records import canonical
from activity_planning_demo.bundle import make_bundle
from activity_planning_demo.package_bundle import make_package_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("PRT", "ONLINE"), required=True)
    parser.add_argument("--demo", choices=("activity-planning", "activity-package"),
                        default="activity-planning")
    args = parser.parse_args()
    build = make_bundle if args.demo == "activity-planning" else make_package_bundle
    print(canonical(build(args.environment)).decode("utf-8"))


if __name__ == "__main__":
    main()
