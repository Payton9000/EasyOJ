import sqlite3

conn = sqlite3.connect('data/database.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print('Database Tables:')
for table in sorted(tables):
    print(f'  ✓ {table[0]}')

conn.close()
