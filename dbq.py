import sqlite3, sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
con = sqlite3.connect("instance/dermascan.db")
for row in con.execute(sys.argv[1]):
    print(row)
