"""`python -m app` runs the site. By default only this machine can reach it (127.0.0.1);
behind a web server like Caddy, set HOST=0.0.0.0 and FORWARDED_ALLOW_IPS to the proxy's address."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        # Trust X-Forwarded-For/Proto only from the proxy, so login throttling sees real visitor addresses.
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        server_header=False,
    )
