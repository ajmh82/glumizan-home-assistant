# GluMizan Home Assistant custom integration

This is a standalone Home Assistant custom component. Copy the `custom_components/glumizan` directory into a Home Assistant configuration directory only after a separate HA deployment target and TLS endpoint have been approved. It is intentionally not deployed by GluMizan application releases.

At installation, configure the GluMizan HTTPS API URL and the installation-specific callback trust secret generated in GluMizan. To repair an existing pairing, use **Configure** on the existing GluMizan entry; do not add a second integration. GluMizan associates the Home Assistant installation with only its authorized patient and caregiver grants; no caregiver UUID is entered in Home Assistant. The Home Assistant bearer token remains server-side in GluMizan; do not enter or store it in this component.

The component consumes GluMizan's authenticated, provider-neutral event bridge. Patient aliases are non-PII and are used only for device/entity identity; GluMizan remains the authorization and clinical source of truth.

For compatible glucose cards, the Glucose sensor keeps its canonical `trend` and `measured_at` attributes and also exposes `direction` and `measurement_timestamp`. Both compatibility attributes are deterministic representations of the same GluMizan CGM reading; `update_source` is diagnostic metadata and never replaces user-facing freshness.
