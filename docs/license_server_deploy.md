# SagittaDB License Server Deployment

The license server is an internal service for commercial operations. It signs
licenses, manages customers and activation codes, and serves a simple web admin.
Do not deploy it into customer environments.

The source code lives in the private repository:

```text
https://github.com/Lynn-Lee/SagittaDB-License-Server
```

SagittaDB product images only contain the public-key verifier and online
activation client. They do not contain the license server source or private key.

## Environment

```bash
LICENSE_DB_PASSWORD=<strong password>
LICENSE_AUTHORITY_ADMIN_TOKEN=<admin bearer token>
SAGITTADB_LICENSE_PRIVATE_KEY=<Ed25519 private key>
LICENSE_ADMIN_PATH=/<hidden admin path>
LICENSE_SERVER_PORT=8011
```

Generate a keypair with:

```bash
cd backend
./.venv/bin/python ../tools/license_issue.py --generate-keypair
```

Set `LICENSE_PUBLIC_KEY` in SagittaDB customer/internal deployments, and keep
`SAGITTADB_LICENSE_PRIVATE_KEY` only on this internal license server.

## VPS Deployment

```bash
mkdir -p /opt/sagittadb-license-server
cd /opt/sagittadb-license-server
docker compose up -d
```

In production the container should bind only to `127.0.0.1:8011`. Nginx/Xray
publishes the public HTTPS endpoint:

```text
https://sagitta.loveai.asia
```

Open `https://sagitta.loveai.asia/<hidden admin path>`, enter the admin token,
then create:

1. customer
2. activation code
3. SagittaDB online activation from the product license page

## Backup

Back up the PostgreSQL database regularly:

```bash
docker compose exec license_postgres pg_dump -U license sagittadb_license > license-server-$(date +%F).sql
```

## Internal Production Verification

1. Start the license server on the VPS.
2. Configure one internal SagittaDB environment with:
   - `LICENSE_PUBLIC_KEY`
   - `LICENSE_CUSTOMER_ID`
   - `LICENSE_SERVER_URL=https://sagitta.loveai.asia`
   - `LICENSE_SERVER_TOKEN` if an edge proxy injects or requires one for product endpoints.
3. Create a customer and activation code in the license server web admin.
4. Activate from SagittaDB System Management -> License.
5. Run `deploy/customer/verify-license.sh <activation-code> <customer-id>`.
6. Suspend the activation code in the license server and run SagittaDB license refresh; core APIs should be blocked.
7. Restore the activation code to active or create a new code, activate again, and confirm core APIs recover.
