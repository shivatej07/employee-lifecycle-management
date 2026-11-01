from datetime import date
def delay_days(original,start): return max(0,(date.fromisoformat(start)-date.fromisoformat(original)).days)
def task_completion_percent(rows):
    rows=list(rows); return round(100*sum(r['status']=='DONE' for r in rows)/len(rows),2) if rows else 0.0
def is_overdue(due,status,as_of='2026-10-22'): return status not in {'DONE','CANCELLED'} and due<as_of
def grant_is_eligible(status,start,as_of,approved): return status in {'PRE_BOARDING','ACTIVE'} and start<=as_of and approved
