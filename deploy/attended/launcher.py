"""One image, four roles: command dispatcher for the attended deployment.

Commands:
  serve-runtime   uvicorn deploy.attended.runtime_app:create_app_from_environment
  serve-bside     uvicorn deploy.attended.bside_app:create_app_from_environment
  seed            apply platform schemas, then the reviewed asset seed
  scheduler       run the scheduler-mq loops
"""

from __future__ import annotations

import sys


def main() -> None:
    import uvicorn

    command = sys.argv[1] if len(sys.argv) > 1 else "--help"
    if command == "serve-runtime":
        uvicorn.run(
            "deploy.attended.runtime_app:create_app_from_environment",
            host="127.0.0.1", port=8765, factory=True, log_level="info",
        )
    elif command == "serve-bside":
        uvicorn.run(
            "deploy.attended.bside_app:create_app_from_environment",
            host="127.0.0.1", port=8767, factory=True, log_level="info",
        )
    elif command == "seed":
        from deploy.attended import seed as platform_seed
        from deploy.mvp import seed as asset_seed

        platform_seed.main()
        asset_seed.main()
    elif command == "scheduler":
        from a2flow_scheduler.main import main as scheduler_main

        scheduler_main()
    else:
        raise SystemExit(
            "usage: launcher serve-runtime|serve-bside|seed|scheduler"
        )


if __name__ == "__main__":
    main()
