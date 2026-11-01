from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
EXPORTS=DATA/"exports"
GROUND_TRUTH=DATA/"ground_truth"
REPORTS=ROOT/"reports"
AS_OF=os.getenv("AS_OF_DATE","2026-10-22")
SEED=int(os.getenv("DEFAULT_SEED","20261022"))
DB=Path(os.getenv("DATABASE_PATH",str(ROOT/"app.db")))
SECRET=os.getenv("APP_SECRET_KEY","development-only-change-this-secret-key")
