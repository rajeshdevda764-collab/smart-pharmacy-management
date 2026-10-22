# SmartPharm upgrade guide

## What changed
- PDF invoice downloads (`/invoice/<id>/pdf`)
- Analytics (`/analytics`) and CSV sales export
- Low-stock, expired, and expiring inventory alerts (`/alerts`)
- Inventory category/status/search filters and status badges

## Preserve your data
This ZIP intentionally does **not** include `.env`, passwords, MySQL data, or your virtual environment. **Do not delete or recreate your MySQL database.** No schema migration is required; the existing User, Medicine, Customer, Sale, and SaleItem models are unchanged.

1. Make a backup of your working project folder and MySQL database.
2. Stop the current Waitress server (Ctrl+C in the Command Prompt running it).
3. Extract this ZIP into a **new** folder, rather than overwriting the working project.
4. Copy **only your existing `.env`** from the working folder into the new `smart_pharmacy` folder. Do not share it. Verify it points to `127.0.0.1:3307/smart_pharmacy`.
5. In the new folder's Command Prompt:
   ```cmd
   py -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   venv\Scripts\python.exe -m waitress --listen=127.0.0.1:5055 app:app
   ```
6. Open `http://127.0.0.1:5055/login`, sign in with your **existing** admin account, and check the Analytics and Stock alerts links.

**Do not run `seed-demo` or `create-admin` again** if your MySQL database already has those records.

PDF invoices use ReportLab; amounts are shown in INR using Latin text to ensure the built-in PDF font renders reliably. CSV exports are UTF-8 with BOM for Excel compatibility.
