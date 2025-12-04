from app.database import get_connection
from werkzeug.security import generate_password_hash

def create_users():
    conn = get_connection()
    if conn is None:
        print("DB connection failed")
        return

    cur = conn.cursor()
    users = [
        ('Alice Admin', 'admin@example.com', '1111111111', 'admin', None, None, '2020-01-01', 'Active', generate_password_hash('adminpass')),
        ('Hannah HR', 'hr@example.com', '2222222222', 'hr', None, None, '2021-06-01', 'Active', generate_password_hash('hrpass')),
        ('Ethan Employee', 'emp@example.com', '3333333333', 'employee', None, None, '2022-03-15', 'Active', generate_password_hash('emppass')),
    ]

    for u in users:
        try:
            cur.execute("""
                INSERT INTO employee1 (name,email,phone,role,department_id,salary,joining_date,status,password_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, u)
            print("Inserted:", u[1])
        except Exception as e:
            print("Skipping (may exist):", u[1], "->", e)

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    create_users()
