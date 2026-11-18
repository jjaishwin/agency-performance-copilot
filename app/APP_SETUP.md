# Deal Desk app: setup

A Databricks App (Streamlit) for account managers, with two tabs:
- **Deal what-if:** pick a managed account, see attainment and share vs fair share, and test contract targets of QSI + 0/5/10/15. This is the "modeling a good deal" step of the corporate deal lifecycle.
- **Ask Genie:** ask the Agency Performance Copilot Genie Agent a question, and see the answer, the table and the SQL it ran.

## Deploy

**Option A, with the bundle (recommended):** `databricks bundle deploy` creates the app with the warehouse resource and user-authorization scopes (see `databricks.yml`). Then `databricks bundle run deal_desk` starts it.

**Option B, by hand:**
1. **Compute → Apps → Create app → Custom.** Name it `deal-desk`.
2. **Resources:** add your **SQL warehouse** with key `sql-warehouse` and permission **Can use**.
3. **Settings → User authorization:** add scopes **`sql`** and **`genie`**. The app then runs queries as the signed-in user.
4. Deploy from the `app/` folder of your Git folder.

## Permissions: how security works

With **user authorization on** (the default in the bundle), the app queries as the person using it. The Unity Catalog row filter from notebook 05 shows each account manager only the accounts in their region, with no security code in the app. You'll see your own email at the top of the page.

The app caches results **per user**. A shared cache would show one user's row-filtered results to the next user, which is a real data leak in many internal apps.

With user authorization **off**, the app runs as its service principal, which needs:
```sql
GRANT USE CATALOG ON CATALOG workspace TO `<app-service-principal>`;
GRANT USE SCHEMA ON SCHEMA workspace.gold TO `<app-service-principal>`;
GRANT SELECT ON SCHEMA workspace.gold TO `<app-service-principal>`;
INSERT INTO workspace.gold.am_region_access VALUES ('<app-service-principal-application-id>', 'ALL');
```
Without the last line, the row filter hides every account, and the app shows a message saying so.

Free Edition allows a small number of apps, and they stop after a period of inactivity. Start it again before a demo. If user authorization isn't available on your workspace, use the service-principal path and say so.
