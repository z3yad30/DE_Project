# California Electricity Demand and Weather Analytics

End-to-end data engineering pipeline: ingestion, cleaning, PostgreSQL storage, data quality checks, Kestra orchestration, and a BI dashboard.

## Team

| Name | ID |
|------|----|
| Hisham Wael Hosny | 692300279 |
| Zeyad Mohamed | 692300066 |
| Mohamed Mostafa | 692300110 |
| Basel Tamer Fathy | 692300055 |
| Fatma Shrief | 692300201 |

## Running the Extraction Script

This project includes a Python extraction script that downloads the CAISO Hourly Demand + Weather dataset from Kaggle and extracts the CSV file into the local raw data directory.

### 1. Prerequisites

Before running the extraction script, make sure you have:

- Python 3.11 or later
- Git
- A Kaggle account with access to the dataset

### 2. Clone the Repository

```bash
git clone <repo-url>
cd <repo-folder>
```

### 3. Create and Activate a Virtual Environment

**Linux / WSL:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies

The extraction script requires the `requests` package.

```bash
python -m pip install requests
```

### 5. Configure Kaggle Credentials

Create your local environment file:

```bash
cp .env.example .env
```

Open `.env` and fill in your Kaggle credentials:

```env
KAGGLE_USERNAME=your_kaggle_username
KAGGLE_KEY=your_kaggle_api_key
KAGGLE_DATASET=arimancy/caiso-hourly-demand-weather

MAX_RETRIES=3
RAW_DIR=data/raw
```

**Where can you get your Kaggle credentials?**

1. Log in to your Kaggle account.
2. Open your account settings.
3. Navigate to the API section.
4. Generate an API token and obtain the credentials required by this project.
5. Add them to your local `.env` file.

**Important:**
- Never commit `.env` or share your Kaggle credentials.
- `.env` is already included in `.gitignore`.
- Keep `.env.example` as a template with placeholder values.

### 6. Load Environment Variables

The extraction script reads configuration from environment variables. It does not automatically load `.env`, so export the variables before running it.

**Linux / WSL:**

```bash
set -a
source .env
set +a
```

If you encounter a `command not found` error or see `%0D` at the end of the Kaggle request URL, your `.env` file may have Windows line endings. Fix them using:

```bash
sed -i 's/\r$//' .env
```

Then load the environment variables again.

**Windows PowerShell:**

```powershell
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
```

### 7. Run the Extraction Script

From the repository root, execute:

```bash
python scripts/extract.py
```

The script will:

1. Connect to the Kaggle dataset API.
2. Download the dataset archive.
3. Extract the CSV file.
4. Calculate its SHA-256 checksum and file size.
5. Save the extracted file in `data/raw/`.

### 8. Verify the Output

After successful execution, check the raw data directory:

```bash
ls -lh data/raw/
```

You should find a CSV file with a name similar to:

```text
caiso_hourly_<timestamp>.csv
```

The timestamp is generated automatically during extraction.

### Troubleshooting

| Error | Possible Cause | Solution |
|---|---|---|
| Missing Kaggle credentials | Environment variables are not loaded | Re-run the environment loading commands |
| HTTP 403 | Invalid credentials, insufficient dataset access, or malformed request URL | Check Kaggle credentials, dataset access, and `.env` formatting |
| HTTP 404 | Incorrect dataset identifier | Verify `KAGGLE_DATASET` |
| Connection timeout | Network or Kaggle API connectivity issue | Check your internet connection and retry |
| `command not found` when sourcing `.env` | Possible Windows line endings or malformed `.env` entries | Run `sed -i 's/\r$//' .env` |

