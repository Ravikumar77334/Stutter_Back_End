import psycopg2

def connection():
    conn = psycopg2.connect(
        host= "localhost",
        database = "Stutter",
        user = "postgres",
        password = "7733",
        port = "5432"
    )
    
    return conn