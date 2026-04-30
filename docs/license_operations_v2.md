# SagittaDB License Operations v2

This document describes the first online license operations loop. Offline signed
license import remains supported for isolated customer networks.

## Product-Side Configuration

Set these environment variables in the customer deployment:

```bash
LICENSE_PUBLIC_KEY=<your Ed25519 public key>
LICENSE_CUSTOMER_ID=<customer id>
LICENSE_SERVER_URL=https://sagitta.loveai.asia
LICENSE_SERVER_TOKEN=<optional bearer token>
LICENSE_AUTO_REFRESH_ENABLED=true
LICENSE_RENEWAL_NOTIFY_DAYS=30,7
```

When `LICENSE_SERVER_URL` is empty, offline import still works and online
activation/refresh returns a clear configuration error.

## Internal Authority Tool

Generate keys:

```bash
python3 tools/license_authority.py --generate-keypair
```

Create an activation code:

```bash
export SAGITTADB_LICENSE_PRIVATE_KEY=<private key>
python3 tools/license_authority.py create-activation \
  --db /secure/license-authority.json \
  --customer-id acme \
  --company-name "Acme Corp" \
  --days 365 \
  --max-instances 20 \
  --max-users 200
```

View the authorization ledger:

```bash
python3 tools/license_authority.py list --db /secure/license-authority.json
python3 tools/license_authority.py audit --db /secure/license-authority.json --limit 50
```

Renew or change limits:

```bash
python3 tools/license_authority.py renew \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --days 365 \
  --max-instances 50 \
  --max-users 500
```

For the formal license server, use the private repository
`https://github.com/Lynn-Lee/SagittaDB-License-Server` and
`docs/license_server_deploy.md`. The helper below remains useful for local
development and migration testing only.

Start the private helper API:

```bash
export SAGITTADB_LICENSE_PRIVATE_KEY=<private key>
export SAGITTADB_LICENSE_AUTHORITY_TOKEN=<shared internal token>
python3 tools/license_authority.py serve --db /secure/license-authority.json --host 0.0.0.0 --port 8011
```

Suspend or revoke an activation:

```bash
python3 tools/license_authority.py set-status \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --status revoked
```

Export the last issued signed license for offline customers:

```bash
python3 tools/license_authority.py export-license \
  --db /secure/license-authority.json \
  --activation-code <code> \
  --out acme-license.json
```

## Customer Flow

- Customer enters the activation code in System Management -> License.
- SagittaDB calls `/api/v1/licenses/activate`, receives a signed license, then verifies it locally with the embedded public key.
- Refresh calls `/api/v1/licenses/refresh`. If the authority returns `revoked` or `suspended`, SagittaDB marks the local license invalid.
- SagittaDB shows a renewal warning when a trial or paid license has 30 days or fewer remaining, and a critical warning at 7 days or fewer.
- Offline license files continue to use `tools/license_issue.py`.

## Internal Production Verification

1. Deploy the authority service on the VPS with a private key and token.
2. Configure one internal SagittaDB production-like instance with `LICENSE_PUBLIC_KEY`, `LICENSE_SERVER_URL`, `LICENSE_SERVER_TOKEN`, and `LICENSE_CUSTOMER_ID`.
3. Create an activation code and activate it from the SagittaDB license page.
4. Run a refresh from the license page and confirm `last_online_check_at` updates.
5. Set the activation to `suspended`, refresh again, and confirm SagittaDB marks the license invalid and blocks core APIs.
6. Set it back to `active` or create a new activation code, activate again, and confirm core APIs recover.
