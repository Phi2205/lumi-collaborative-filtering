# Troubleshooting

## Lỗi kết nối database

### 1. Password authentication failed

**Nguyên nhân:**
- Password trong `.env` không đúng
- Password có ký tự đặc biệt chưa được URL encode
- User không có quyền truy cập database

**Giải pháp:**

#### a) Kiểm tra password đúng chưa
```bash
# Test connection bằng psql
psql "postgresql://user:password@host:5432/dbname"
```

#### b) URL encode password nếu có ký tự đặc biệt

Nếu password có các ký tự đặc biệt, cần encode:
- `@` → `%40`
- `#` → `%23`
- `%` → `%25`
- `&` → `%26`
- `+` → `%2B`
- `=` → `%3D`
- `?` → `%3F`
- `/` → `%2F`
- `:` → `%3A`
- ` ` (space) → `%20`

**Ví dụ:**
```
Password gốc: p@ss#123
Password encoded: p%40ss%23123

DATABASE_URL=postgresql://user:p%40ss%23123@host:5432/dbname
```

**Hoặc dùng Python để encode:**
```python
from urllib.parse import quote_plus
password = "p@ss#123"
encoded = quote_plus(password)
print(encoded)  # p%40ss%23123
```

#### c) Kiểm tra user và quyền
```sql
-- Trong psql
\du  -- List users
SELECT * FROM pg_user WHERE usename = 'phiduong';
```

### 2. Connection refused / Could not connect

**Nguyên nhân:**
- Host/port sai
- Database server không chạy
- Firewall block connection
- IP không được whitelist

**Giải pháp:**
1. Kiểm tra host/port trong `.env`
2. Test connection từ terminal:
   ```bash
   telnet host 5432
   # hoặc
   nc -zv host 5432
   ```
3. Kiểm tra firewall rules trên database server
4. Thêm IP vào whitelist (nếu dùng managed database như Render, AWS RDS)

### 3. Database does not exist

**Giải pháp:**
```sql
-- Tạo database
CREATE DATABASE lumi_cf_dev;

-- Hoặc dùng database có sẵn
-- Update DATABASE_URL trong .env
```

### 4. SSL required

Nếu database yêu cầu SSL (như Render PostgreSQL):
```
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
```

## Kiểm tra .env file

Đảm bảo file `.env` có format đúng:
```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
MODEL_PATH=artifacts/model.joblib
```

**Lưu ý:**
- Không có khoảng trắng quanh dấu `=`
- Không có quotes (`"` hoặc `'`) trừ khi cần thiết
- Password có ký tự đặc biệt phải URL encode
