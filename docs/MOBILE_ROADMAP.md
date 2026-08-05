# Mountain of Helicon mobile roadmap

## Decision

Ship the existing React dashboard as a mobile-first progressive web app (PWA)
before building a native client.

The core phone experience already exists: responsive navigation, touch-sized
review actions, and phone-specific Cockpit behavior. A second UI in Swift,
Kotlin, React Native, Tauri, or Capacitor would duplicate that work before
proving that a browser capability is blocking the product.

The PWA must be served over HTTPS. Do not expose a personal Helicon store on a
public IP just to reach it from a phone. The current optional
`HELICON_PASSWORD` bearer check is API-only and has no dashboard sign-in flow,
so it is not yet a safe remote-access product boundary.

## Product target

Mountain of Helicon becomes the place an operator can open from a phone
notification, understand one grounded exception, rule on it with a thumb, and
leave in under a minute. Desktop remains the deep inspection and configuration
surface.

Success is not “the desktop page fits at 390 px.” Success is:

- install from the browser and launch without browser chrome;
- land on the exact finding or run that requested attention;
- make one reversible ruling without horizontal page movement;
- see a receipt and know whether the next agent received the correction;
- keep private memory private if the phone is lost or the URL leaks.

## Milestones

### M0 — Installable mobile web foundation (started)

- Add a web app manifest, standalone display metadata, theme, icon, and useful
  shortcuts.
- Make the Doorway summary, repository rows, paths, verdict rows, and actions
  reflow at narrow widths.
- Use the external product name, Mountain of Helicon, in install surfaces.
- Validate the production build and the key 390 px journeys against real or
  explicitly seeded demo data.

Exit gate: install metadata is valid; Doorway and Lab have no document-level
horizontal overflow at 390 px; all primary actions are at least 44 px on a
coarse pointer.

### M1 — Secure reachability

- Put the self-hosted dashboard behind HTTPS on a private network or an
  authenticated reverse proxy.
- Replace the raw bearer-password option with a real login/session boundary:
  secure, HTTP-only, same-site cookies; CSRF protection on mutations; rate
  limits; explicit logout; short-lived sessions.
- Restrict CORS to configured origins instead of `*`.
- Add a “remote access doctor” check that refuses an unsafe public bind and
  explains the remedy.
- Publish two supported recipes: private mesh/VPN for local-first stores and a
  hardened single-tenant cloud deployment.

Exit gate: a phone can connect over HTTPS without exposing an unauthenticated
memory API, and every write has an authenticated audit receipt.

### M2 — The one-minute ruling loop

- Give findings and governed runs durable URLs, not only tab hashes.
- Add next/previous queue navigation and preserve scroll/filter state.
- Make all mutation states resilient to double taps, weak networks, retries,
  and stale records.
- Add a compact receipt screen with undo and “correction delivered” status.
- Run accessibility checks for screen readers, focus order, contrast, text
  scaling, reduced motion, and landscape.

Exit gate: open deep link → inspect evidence → rule → receipt → undo works on
iOS Safari and Android Chrome under throttled mobile networking.

### M3 — Attention without surveillance

- Add opt-in Web Push for new critical findings and governed runs that need a
  ruling.
- Send identifiers and counts in push payloads, never memory text.
- Support quiet hours, per-project notification controls, deduplication, and
  escalation only when state is still current.
- Add an in-app notification ledger so every push has a server-side reason.

Exit gate: tapping a notification opens the exact current item; dismissed,
resolved, or superseded items do not re-alert.

### M4 — Resilient field use

- Cache only the app shell by default.
- Offer an explicit encrypted “available offline” mode for a bounded,
  read-only queue snapshot; never cache personal evidence silently.
- Queue rulings made during a transient disconnect with an idempotency key and
  require conflict review if server state changed.
- Add share-target support for sending an agent transcript or receipt into
  Helicon, with a confirmation screen before ingestion.

Exit gate: network loss cannot duplicate a ruling, leak evidence through a
shared device cache, or show stale state as current.

### M5 — Native capability gate

Instrument PWA usage and record concrete browser limitations. Introduce a thin
Capacitor shell only if measured demand requires capabilities the PWA cannot
reliably provide, such as stronger background delivery, OS-level secure
storage, or managed enterprise distribution.

The shell must reuse the React application and API contract. Native-only code
is limited to capability adapters (notifications, secure credentials, share
sheet, biometrics), with the web implementation retained as the default.

Exit gate: each native plugin maps to a measured limitation and has a web
fallback. No duplicated product screens.

## Immediate execution order

1. Complete M0 and test the built app at 390 px and desktop width.
2. Implement M1 before publishing a personal store beyond localhost.
3. Build durable item URLs and network-safe ruling mutations from M2.
4. Pilot opt-in push with metadata-only payloads.
5. Revisit native packaging only after the capability gate has evidence.

## Measures

- median time from deep link to completed ruling;
- completion and undo rate by viewport;
- horizontal-overflow and failed-mutation count;
- notification open-to-ruling conversion and duplicate-alert rate;
- install rate among repeat mobile operators;
- number of native-only capability requests with reproducible browser limits.
