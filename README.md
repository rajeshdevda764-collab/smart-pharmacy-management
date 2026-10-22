# SmartPharm — Smart Pharmacy Management System

Full-stack Flask + MySQL pharmacy management project with a responsive dashboard, authentication, inventory, expiry and low-stock alerts, customer directory, transaction-safe billing, sales reports, and printable invoices.

## Requirements
- Python 3.10+
- MySQL 8+ (running locally)
- Internet connection to load Chart.js from CDN (the rest of the app works offline)

## Installation

1. Extract the ZIP and open a terminal inside `smart_pharmacy`.
2. Create a MySQL database:

   ```sql
   CREATE DATABASE smart_pharmacy CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

3. Create a Python virtual environment and install dependencies:

   **Windows PowerShell:**
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, replace the MySQL password and secret key. If your MySQL password includes `@`, `#`, or `:`, URL-encode it in `DATABASE_URL`. Use a dedicated database account for production.
5. Run:

   ```bash
   flask --app app init-db
   flask --app app create-admin
   flask --app app seed-demo
   flask --app app run
   ```

6. Open **http://127.0.0.1:5000/login** and sign in with the admin credentials you created.

## Demonstration flow
1. Log in → inspect dashboard cards, low-stock alert, and expiry alert.
2. Open Inventory → add a medicine → edit stock and price.
3. Open Customers → create a customer.
4. Open New Billing → select a customer, add medicine(s), choose quantities, and complete sale.
5. Print or save the resulting invoice as PDF using your browser.
6. Return to Inventory to verify stock deduction; check Sales History and dashboard revenue.

## Notes / limitations
- Stock checks and deductions happen in a single database transaction with MySQL row locks.
- Expired medicines cannot be billed. Low stock and expiry alerts are displayed on the dashboard.
- Price is stored in INR. The sample billing uses the medicine price as the final price; it **does not implement GST, tax invoices, prescriptions, or payment processing**.
- Dashboard sales chart covers the previous 7 calendar days; timestamps are stored in UTC.
- This is an academic demonstration, **not a certified pharmacy or clinical system**. Do not use it for real patient records or regulated dispensing without appropriate legal, security, privacy, and prescription controls.
- For production, add CSRF protection, HTTPS, secure cookie settings, role-based authorization, migrations, audit logging, backups, pagination, and compliance controls. The project uses one admin role only.
- Do not commit your `.env` or database credentials to a public repository.
