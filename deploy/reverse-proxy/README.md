# Public HTTPS edge

The application hosts bind to loopback. The example Nginx template fronts the operator stack; a self-host gateway should instead be proxied through its published loopback port. Replace only `${DOMAIN}` (not Nginx variables such as `$request_uri`) and adjust upstream ports to your installation. Keep private keys outside the source tree.

1. Point the chosen DNS name at the host. Back up current Nginx configuration, verify `nginx -t`, and provision an HTTP ACME webroot at `/var/lib/a2flow-acme` without changing application upstreams.
2. Use an isolated maintained Certbot installation to issue a publicly trusted certificate with `certbot certonly --webroot -w /var/lib/a2flow-acme -d YOUR_DOMAIN`. Configure an operator email or explicitly select no-email account mode. Never substitute a self-signed public certificate or disable verification.
3. Render `nginx.conf.template`, install `proxy-headers.conf` as `/etc/nginx/a2flow-proxy-headers.conf`, and configure M/B browser-origin settings to the exact HTTPS origin. Set `A2FLOW_AUTH_TRUSTED_PROXIES=127.0.0.1,::1` only where this trusted proxy is the direct caller. The edge overwrites the dedicated client-IP header. The Java account proxy preserves this bounded chain.
4. Apply the account-guard migration before starting new account/B code. Verify valid login, `Secure; HttpOnly; SameSite` cookies, cross-origin rejection and shared 429 admission. Then enable HTTP-to-HTTPS redirect. Do not process password POST bodies at the HTTP endpoint during migration.
5. Run `certbot renew --dry-run`. Enable an OS timer to renew twice daily with randomized delay. The renewal deploy hook must run `nginx -t && systemctl reload nginx`; failures remain visible in service status/journal. Verify the certificate chain and hostname with a browser or curl, without bypass flags.

Rollback retains previous per-service manifests and proxy configuration. Do not silently revert a protected public origin to HTTP; if HTTPS cannot start, keep the application unavailable until certificate/configuration recovery. Do not enable HSTS preload during initial migration before recovery and domain ownership are verified.

Official references: [Certbot documentation](https://eff-certbot.readthedocs.io/en/stable/using.html), [HTTP-01 challenge](https://letsencrypt.org/docs/challenge-types/).
