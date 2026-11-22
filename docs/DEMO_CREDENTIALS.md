# Demo Credentials

All accounts below are **fictional demonstration identities** created by `database/seed.sql`. The emails
use the reserved `example.com` domain. The passwords are for the local demo only: the database stores just
their scrypt hashes. Change or remove these accounts before any real deployment.

| Role | Name | Email | Password | Owns |
|---|---|---|---|---|
| admin | Avery Morgan | `avery.morgan@example.com` | `Admin#2026` | Trip 1 |
| user | Jordan Rivera | `jordan.rivera@example.com` | `User#2026` | Trip 2 |
| user | Taylor Brooks | `taylor.brooks@example.com` | `User#2026` | Trip 3 |
| user | Casey Nguyen | `casey.nguyen@example.com` | `User#2026` | Trip 4 |
| user | Aisha Khan | `aisha.khan@example.com` | `User#2026` | Trip 5 |
| guest | Daniel Chen | `daniel.chen@example.com` | `Guest#2026` | Trip 6 (read-only) |
| guest | *(anonymous)* | "Continue as guest" button | — | — |

## What each role can do

| Capability | admin | user | guest |
|---|---|---|---|
| Sign in / sign out | ✔ | ✔ | ✔ |
| View locations, observations, analytics charts | ✔ | ✔ | ✔ |
| Database Explorer | all 10 views, all rows | all 10 views; views 1, 4, 8, 10 show only the user's own rows | views 2, 3, 5, 6, 7, 9 (no personal data) |
| CSV / PDF export | ✔ | ✔ (same scoping as the views) | ✔ (permitted views only) |
| Create trips, generate/add/select routes | ✔ (any user) | ✔ (own) | ✘ |
| Fetch and save live route weather | ✔ | ✔ (own routes) | ✘ (display-only location lookup allowed) |
| Add locations | ✔ | ✔ | ✘ |
| Edit or delete locations | ✔ | ✘ | ✘ |
| Preferences, saved places, feedback | ✔ (all) | ✔ (own) | ✘ |
| Manage users, roles, segments, observations, all tables | ✔ | ✘ | ✘ |

To restore the original demo data at any time, run `python scripts\init_db.py`.
