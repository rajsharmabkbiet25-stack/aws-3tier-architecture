from flask import Flask, jsonify
import pymysql

app = Flask(__name__)

def get_db():
    return pymysql.connect(
        host="<rds-endpoint>",
        user="admin",
        password="yourpassword",
        database="appdb"
    )

@app.route('/')
def home():
    return jsonify({"status": "healthy", "message": "3-tier app running"})

@app.route('/users')
def get_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

@app.route('/adduser')
def add_user():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name, email) VALUES ('Raj', 'raj@example.com')")
    conn.commit()
    conn.close()
    return jsonify({"message": "User added successfully"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
