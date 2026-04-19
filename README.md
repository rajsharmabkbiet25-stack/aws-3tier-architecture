# 3-Tier AWS Architecture — Python Flask + RDS MySQL

A production-grade 3-tier web application deployed on AWS with full network isolation, IAM roles, and a working REST API connected to a managed MySQL database.

## Architecture Overview

```
Internet
    ↓
Route53 (rajtestsite.com)
    ↓
Application Load Balancer — public subnets (us-east-1a, us-east-1b)
    ↓
EC2 Flask API — private subnet (no public IP)
    ↓
RDS MySQL — private subnet (no public access)
```

## Tech Stack

| Layer | Service | Details |
|---|---|---|
| DNS | Route53 | A record → ALB |
| Load Balancer | ALB | HTTP:80, health checks |
| Compute | EC2 (t2.micro) | Python Flask, Amazon Linux 2023 |
| Database | RDS MySQL 8.4 | Single AZ, db.t4g.micro |
| Network | Custom VPC | 10.0.0.0/16, 4 subnets, 2 AZs |
| Access | SSM Session Manager | No SSH, no bastion host |
| Identity | IAM Role | EC2 → S3 + SSM (no hardcoded keys) |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/users` | GET | Fetch all users from RDS |
| `/adduser` | GET | Insert a test user into RDS |

## Security Model

```
ALB Security Group  → accepts port 80 from 0.0.0.0/0 (internet)
EC2 Security Group  → accepts port 80 from ALB security group only
RDS Security Group  → accepts port 3306 from EC2 security group only
```

Internet cannot reach EC2 or RDS directly. Zero hardcoded credentials — IAM role used instead.

---

## Deployment Steps

### Step 1 — VPC Setup

1. Go to VPC → Create VPC → select **VPC and more**
2. Name: `raj-3tier-vpc`, CIDR: `10.0.0.0/16`
3. Set 2 AZs, 2 public subnets, 2 private subnets
4. NAT Gateway: In 1 AZ
5. Click Create VPC

### Step 2 — Security Groups

Create 3 security groups inside `raj-3tier-vpc`:

**ALB SG (`raj-alb-sg`)**
- Inbound: HTTP port 80 from `0.0.0.0/0`

**EC2 SG (`raj-ec2-sg`)**
- Inbound: HTTP port 80 from `raj-alb-sg`

**RDS SG (`raj-rds-sg`)**
- Inbound: MySQL port 3306 from `raj-ec2-sg`

### Step 3 — RDS Database

1. RDS → Create database → MySQL 8.4
2. Instance: `db.t4g.micro`, Single AZ
3. VPC: `raj-3tier-vpc`
4. DB Subnet Group: create one with both private subnets
5. Public access: **No**
6. Security group: `raj-rds-sg`

### Step 4 — EC2 App Server

1. Launch EC2 → Amazon Linux 2023, t2.micro
2. VPC: `raj-3tier-vpc`, private subnet
3. Auto-assign public IP: **Disabled**
4. Security group: `raj-ec2-sg`
5. IAM role: attach role with `AmazonSSMManagedInstanceCore` + `AmazonS3ReadOnlyAccess`

### Step 5 — Flask App Setup (via SSM)

Connect to EC2 via SSM Session Manager (no SSH needed):

```bash
sudo su
dnf update -y
dnf install python3 python3-pip -y
pip3 install flask pymysql
dnf install mariadb105 -y
```

Connect to RDS and create database:

```bash
mysql -h <rds-endpoint> -u admin -p
```

```sql
CREATE DATABASE appdb;
USE appdb;
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100)
);
ALTER USER 'admin'@'%' IDENTIFIED WITH mysql_native_password BY 'yourpassword';
FLUSH PRIVILEGES;
exit
```

Create Flask app:

```python
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
```

Run the app:

```bash
python3 app.py
```

### Step 6 — Application Load Balancer

1. EC2 → Load Balancers → Create → Application Load Balancer
2. Name: `raj-alb`, Internet-facing, IPv4
3. VPC: `raj-3tier-vpc`, select both **public subnets**
4. Security group: `raj-alb-sg`
5. Create Target Group → Instances → port 80 → register `raj-app-server`
6. Set listener to forward to target group
7. Create load balancer

### Step 7 — Route53

1. Route53 → Hosted zones → Create hosted zone
2. Domain: your domain, Public
3. Create A record → Alias → Application Load Balancer → select `raj-alb`

### Step 8 — Test

```
http://<alb-dns>/          → {"status": "healthy"}
http://<alb-dns>/adduser   → {"message": "User added successfully"}
http://<alb-dns>/users     → [[1, "Raj", "raj@example.com"]]
```

---

## Cost Estimate (us-east-1, monthly)

| Service | Spec | Est. Cost |
|---|---|---|
| EC2 | t2.micro (on-demand) | ~$8.50/mo |
| RDS | db.t4g.micro Single AZ | ~$12.50/mo |
| ALB | ~10GB data processed | ~$18.00/mo |
| NAT Gateway | ~10GB data | ~$35.00/mo |
| Route53 | 1 hosted zone + queries | ~$0.55/mo |
| Data Transfer | minimal | ~$1.00/mo |
| **Total** | | **~$75/mo** |

> Note: Using Free Tier eligible instances (t2.micro EC2, db.t4g.micro RDS) reduces cost significantly for the first 12 months. NAT Gateway is the biggest cost driver — consider removing it when not needed.

**Cost optimization tips:**
- Stop EC2 and RDS when not in use
- Delete NAT Gateway when not needed (biggest saver)
- Use Reserved Instances for 40-60% savings in production

---

## Key Learnings

- Private subnets prevent direct internet access to app and database tiers
- Security groups create a chain of trust between tiers — no direct internet to EC2 or RDS
- IAM roles eliminate the need for hardcoded AWS credentials
- SSM Session Manager allows secure EC2 access without opening port 22
- ALB health checks require a `/` route returning 200 — 404 marks target unhealthy

## Author

Raj Sharma — IT Support Executive at SITA, Chandigarh Airport  
AWS Certified Solutions Architect – Associate  

