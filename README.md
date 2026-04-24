# Advanced ERP - Flask 

Minimal Flask-based ERP module (inventory + dashboard) scaffolded with a pink UI theme. Uses SQLite for local development.

Quick start (Windows PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
$env:FLASK_APP = 'run.py'
flask init-db
python run.py
```

Quick start (macOS / Linux):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=run.py
flask init-db
python run.py
```

Database: `instance/database.db` (created by `flask init-db`). Default credentials in sample data: `admin` / `admin`.

Files of interest:

- [app/__init__.py](app/__init__.py)
- [app/routes.py](app/routes.py)
- [templates/dashboard.html](templates/dashboard.html)
- [static/css/dashboard.css](static/css/dashboard.css)

PDF / Printing

- The app includes a print-friendly invoice view at `/invoices/<id>/print`.
- For PDF downloads the server can use `pdfkit` + `wkhtmltopdf` if installed. Install `pdfkit` into the venv and `wkhtmltopdf` on your system, then the "Download PDF" button will return a generated PDF. If not available, use the browser Print → Save as PDF from the print view.

Example wkhtmltopdf install (Windows Chocolatey):
```powershell
choco install wkhtmltopdf
```

Then in your venv:
```powershell
python -m pip install pdfkit
```
