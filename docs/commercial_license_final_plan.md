# SagittaDB Commercial License Final Plan

This plan defines the remaining work needed to treat the license platform as a
final commercial system rather than a product-side activation loop.

## Goal

SagittaDB customers should receive versioned product images plus either an
online activation code or an offline signed license. Internally, SagittaDB
operators should be able to create customers, issue and renew licenses, adjust
limits, suspend or revoke access, audit every operation, and recover the license
service without customer data loss.

## P0 Scope

1. Product-side deployment binding
   - Generate and display a deployment fingerprint.
   - Send the fingerprint during online activation and refresh.
   - Reject signed licenses that include a different fingerprint.
   - Store the fingerprint on `license_record` for support and audit.

2. Production license server
   - Maintain customers, activation codes, licenses, status changes, renewals,
     and audit logs in PostgreSQL.
   - Bind activation codes to the first deployment fingerprint unless a
     fingerprint is preconfigured.
   - Reject activation or refresh attempts from a different fingerprint.
   - Support status transitions: `active`, `suspended`, `revoked`.
   - Expose `/api/v1/licenses/activate` and `/api/v1/licenses/refresh` for
     customer deployments.

3. Operator admin
   - Provide a private web admin for customer, activation, renewal, limit, and
     status operations.
   - Require admin authentication and record actor, action, target, old value,
     new value, IP, and timestamp.
   - Hide the admin path and keep the private signing key only on the license
     server.

4. Customer delivery verification
   - Verify online activation, refresh, renewal, suspension, revocation, and
     recovery.
   - Verify offline license import, offline fingerprint mismatch rejection, and
     expired license blocking.
   - Verify customer deployment packages pin versioned images and do not use
     `latest`.

## P1 Scope

1. Edition and package templates
   - Define `trial`, `professional`, and `enterprise` templates.
   - Map each edition to feature sets and default limits.

2. Usage visibility
   - Show current usage next to limits on the customer license page.
   - Show customer activation history and current deployment fingerprint in the
     internal admin.

3. Operations hardening
   - Add backup and restore runbooks for the license server database.
   - Add monitoring for failed activation, refresh errors, nearing-expiry
     licenses, and repeated fingerprint mismatch attempts.
   - Add a customer support checklist for recovering from lost deployment IDs.

## P2 Scope

1. Activation lifecycle polish
   - Support planned deployment migration with explicit unbind or rebind
     approval.
   - Support one customer with multiple purchased deployments.

2. Commercial reporting
   - Export customer/license ledgers.
   - Track expiry windows, active deployments, suspended customers, and revenue
     metadata if needed by sales operations.

## Acceptance Checklist

- New customer can be created and issued an activation code.
- First customer activation binds a deployment fingerprint.
- Same activation code cannot activate a different deployment.
- Refresh returns a renewed signed license for an active activation.
- Suspended or revoked activation blocks protected SagittaDB APIs after refresh.
- Offline signed license with a wrong fingerprint is rejected locally.
- Expired license blocks protected SagittaDB APIs.
- License server private key never appears in customer images, logs, or
  deployment packages.
- All operator writes appear in the license server audit log.
- Customer release package contains version-pinned images, `.env.example`,
  `upgrade.sh`, and `verify-license.sh`.
