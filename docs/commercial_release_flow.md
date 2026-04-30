# SagittaDB Commercial Release Flow

SagittaDB uses a three-line release model:

- `main`: internal source development. It is not a customer production source.
- `release/<major.minor>`: stable commercial release line for customer images.
- `hotfix/<major.minor.patch>`: urgent repair branch cut from the matching release line.

Customers receive only versioned Docker images and the generated customer deployment package. They do not receive source branches.

## Normal Release

```bash
bash scripts/create-release-branch.sh 1.0
git push -u origin release/1.0
git tag v1.0.0
git push origin v1.0.0
```

Pushing `v1.0.0` triggers the commercial release workflow. It builds:

- `ghcr.io/<org>/<repo>-backend:1.0.0`
- `ghcr.io/<org>/<repo>-backend:1.0`
- `ghcr.io/<org>/<repo>-frontend:1.0.0`
- `ghcr.io/<org>/<repo>-frontend:1.0`
- `SagittaDB-Enterprise-v1.0.0.zip`

## Main Development Images

Every push to `main` publishes development images:

- `main-latest`
- `main-<sha>`

Do not use these tags for customer production deployments.

## Release Candidate Images

Every push to `release/1.0` publishes candidate images:

- `release-1.0`
- `release-1.0-<sha>`

Use these only for internal verification or customer pre-release validation.

## Hotfix

```bash
bash scripts/start-hotfix.sh 1.0.4
# fix, test, commit
bash scripts/finish-hotfix.sh 1.0.4
git push origin release/1.0
git push origin main
git push origin v1.0.4
```

The tag push builds the final customer images and deployment package.

## Customer Deployment

Give customers the generated `SagittaDB-Enterprise-v<version>.zip` and the matching license file. The package pins exact image versions in `docker-compose.yml`; customers should not use `latest`.

Customers upgrade with:

```bash
./upgrade.sh <new-version>
```
