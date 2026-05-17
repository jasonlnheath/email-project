import sqlite3, json

conn = sqlite3.connect('/home/jason/relmgr/contacts.db')
conn.row_factory = sqlite3.Row

# Check contacts schema
schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='contacts'").fetchone()
print('Contacts Schema:', schema['sql'] if schema else 'Not found')

# Check contacts data - look for jason
rows = conn.execute("SELECT * FROM contacts WHERE normalized_name LIKE '%jason%' OR LOWER(name) LIKE '%jason%' LIMIT 5").fetchall()
for r in rows:
    d = dict(r)
    print(f'id={d["id"]!r} (type={type(d["id"]).__name__}) name={d.get("normalized_name","")!r}')

# Also check if there's a contact with id='jason'
try:
    row = conn.execute("SELECT * FROM contacts WHERE id='jason'").fetchone()
    print(f"Found contact with id='jason': {row}")
except Exception as e:
    print(f"Error querying id='jason': {e}")

conn.close()
