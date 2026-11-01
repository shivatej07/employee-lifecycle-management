# Build 12 — Responsive UI and Navigation Polish

## Changes
- Reworked shared application CSS for consistent desktop, tablet and mobile layouts.
- Removed the broad `:has(main form)` authentication selector that unintentionally constrained ordinary pages containing forms. Authentication pages now receive an explicit `auth-page` body class.
- Standardized page containers, headings, form sizing, card grids, and responsive navigation.
- Added horizontal overflow handling to wide data tables so columns remain accessible on narrow screens rather than being clipped.
- Added responsive breakpoints for dashboard cards, navigation, forms, and admin panels.
- Added reduced-motion support and improved focus/hover transitions.
- Updated the authenticated navigation label to **Logout** only. The logout route continues to clear the session and redirect to sign-in.
- Updated the logout UI test to assert the requested label and ensure “Switch actor” is absent.

## Verification
Run `python -m onboarding_sim reset-app` followed by `python -m pytest -q`.

The CSS is shared across all role portals and application pages. The authentication layout is isolated so a search/filter form on a normal page cannot accidentally turn the whole page into a narrow login column.
