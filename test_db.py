from db import connection

conn = connection()
print("Connection successfull")
conn.close() 