# GluMizan Home Assistant integration

GluMizan brings authorized patient glucose information, freshness status, active alert episodes, and a caregiver acknowledgement control into Home Assistant. GluMizan remains the clinical and authorization source of truth; Home Assistant devices use non-identifying GluMizan patient aliases.

## Prerequisites

- A working Home Assistant installation with HACS.
- A GluMizan deployment that has enabled the Home Assistant bridge and can reach the Home Assistant instance over HTTPS.
- The dedicated `HOME_ASSISTANT_CALLBACK_SECRET` shared with the GluMizan runtime.
- The UUID of an authorized GluMizan caregiver.

`HOME_ASSISTANT_INTEGRATION_TOKEN` is a Home Assistant bearer token kept only in the GluMizan runtime. Do not enter it into Home Assistant, this integration, YAML, Git, screenshots, or support requests.

## Install with HACS

1. In HACS, add the future dedicated GluMizan integration repository as an **Integration** custom repository.
2. Download **GluMizan** from HACS.
3. Restart Home Assistant.
4. Go to **Settings -> Devices & services -> Add Integration** and select **GluMizan**.
5. Complete the configuration form.

## Manual installation

1. Copy `custom_components/glumizan` from this repository to `/config/custom_components/glumizan`.
2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add Integration** and select **GluMizan**.

## Configuration

The Config Flow asks for exactly these fields:

- `base_url`: the GluMizan HTTPS API URL, normally `https://glumizan.com`.
- `callback_secret`: the dedicated `HOME_ASSISTANT_CALLBACK_SECRET` value. Keep it private; never publish or share it.
- `caregiver_user_id`: the UUID of the GluMizan caregiver authorized for the patient actions.

## Devices and entities

For each provisioned patient, Home Assistant creates a `GluMizan A########` device. The component creates:

- A glucose sensor (`glumizan_A########_glucose`) in `mg/dL`, with trend, measured time, freshness, and episode attributes.
- A diagnostic freshness sensor (`glumizan_A########_freshness`).
- An **I am with the patient** button (`glumizan_A########_acknowledge`) when there is an active episode.

Home Assistant assigns final entity IDs. Trend and episode state are attributes of the glucose sensor; no separate caregiver-information entity is created.

## Updates and removal

After a HACS update, restart Home Assistant. Configuration entries are retained across updates. To remove the integration, remove its config entry in **Settings -> Devices & services**, uninstall it through HACS (or remove `/config/custom_components/glumizan` for a manual install), and restart Home Assistant. Removal does not delete GluMizan clinical data.

## Realtime behavior

GluMizan pushes authenticated batches to the Home Assistant event endpoint at `/api/glumizan/events`; this component does not poll glucose data. New provisioned patients are added automatically when their first event arrives.
