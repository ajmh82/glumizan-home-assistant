# GluMizan Home Assistant v1.4.3

## Improvements
- SSE updates with reconnection reconciliation and safety-focused polling fallback.
- Avoid excessive repeated Cloudflare requests when only long-lived `NO_RECENT_READING` or `SYNC_FAILURE` alerts are active and SSE is connected.
- Retain fast two-second fallback for urgent/unknown alerts, ambiguous episode data, or lost SSE connectivity.
- Do not show an outdated glucose value as a current reading. Disconnected CGM sensors correctly show Glucose as unavailable and Data Freshness as stale.
- Updated authorized account-link and shared viewer panel flows.
- Preserve existing Home Assistant devices, entity IDs, notifications, caregiver permissions, and alert episodes during upgrade.

## Validation
- HACS and Home Assistant Hassfest validation.
- Isolated polling safety regression tests and SSE disconnect/reconnection tests against the production coordinator implementation.
- Observed one-installation backend traffic: Events + Presence requests changed from 604 to 70 across comparable 15-minute windows (88.4% reduction); not a Cloudflare billing measurement.
- Backend telemetry showed active SSE connections but could not independently attribute an individual stream to the Home Assistant instance. Live urgent clinical alarm delivery could not be exercised with the CGM sensor disconnected.

## Upgrade through HACS
1. In **HACS → Integrations**, open the existing **GluMizan** integration.
2. Install/update to the published version **1.4.3**. Allow HACS to refresh release metadata if the update is not yet shown.
3. Restart **Home Assistant Core** to load the new Python code.
4. Check the GluMizan device and its glucose freshness, active alerts, and authorized caregiver entities.

**Do not delete your GluMizan configuration entry, press Add hub, or re-pair your account to update.**

Technical alerts such as `NO_RECENT_READING` and `SYNC_FAILURE` remain visible and are not automatically acknowledged or resolved by this release.
