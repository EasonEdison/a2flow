"""Loopback-only account service; never initializes or migrates account tables."""

from deploy.common.config import _required


def main() -> None:
    import uvicorn
    raw_port = _required("A2FLOW_LISTEN_PORT")
    port = int(raw_port)
    if not 1024 <= port <= 65535 or str(port) != raw_port:
        raise RuntimeError("INVALID_LISTEN_PORT")
    uvicorn.run("deploy.accounts.app:create_app_from_environment", factory=True,
                host="127.0.0.1", port=port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
