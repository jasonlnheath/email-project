import sqlite3, json
conn = sqlite3.connect('/home/jason/relmgr/contacts.db')
conn.row_factory = sqlite3.Row

# Check vip_contacts schema
schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='vip_contacts'").fetchone()
print('Schema:', schema['sql'] if schema else 'Not found')

# Check vip_contacts data
rows = conn.execute('SELECT * FROM vip_contacts LIMIT 10').fetchall()
for r in rows:
    d = dict(r)
    print(f'contact_id={d["contact_id"]!r} (type={type(d["contact_id"]).__name__}) rel={d["relationship_type"]!r}')

conn.close()
