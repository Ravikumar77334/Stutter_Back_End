from db import connection
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from schemas import RegisterModel, LoginModel, ChildModel, AssignDoctorModel, ResultModel

app = FastAPI()
security = HTTPBearer()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated = "auto")

SECRET = "Stuttering"
ALGORITHM = "HS256"

def hash_password(password):
    return pwd_context.hash(password[:72])

def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)

def create_token(data):
    data.update({"exp": datetime.utcnow() + timedelta(hours=1)})
    return jwt.encode(data, SECRET, algorithm = ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return payload

    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post('/register')
def register(user: RegisterModel):
    conn = connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id from users where email = %s", (user.email,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="User is already exist")
    
    hashed = hash_password(user.password)
    
    role = user.role.capitalize()
    cur.execute(
        "INSERT INTO users (email, password, role) VALUES (%s, %s, %s) RETURNING id",
        (user.email, hashed, role) 
    )
    
    user_id = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    return { "msg" : "User created", "user_id": user_id }

def require_role(roles: list):
    def role_checker(user=Depends(verify_token)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user
    return role_checker

@app.post("/add-child")
def add_child(data: ChildModel, user=Depends(require_role(["Parent"]))):
    conn = connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO children (name, age, parent_id) VALUES (%s, %s, %s) RETURNING id",
        (data.name, data.age, user["user_id"])
    )

    child_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return {"msg": "Child added", "child_id": child_id}

@app.post('/login')
def login(user: LoginModel):
    conn = connection()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT id, password, role from users where email=%s",
        (user.email,)
    )
    
    db_user = cur.fetchone()
    
    if not db_user or not verify_password(user.password, db_user[1]):
        raise HTTPException(status_code=401, detail="Invalid creadential")
    
    token = create_token({
        "user_id": db_user[0],
        "role": db_user[2],
        "email": user.email
    })
    
    cur.close()
    conn.close()
    
    return {"access_token": token}

@app.post("/assign-doctor")
def assign_doctor(data: AssignDoctorModel, user=Depends(require_role(["Parent"]))):
    conn = connection()
    cur = conn.cursor()
    
    child_id = data.child_id
    doctor_id = data.doctor_id
    
    cur.execute(
        "SELECT id FROM children WHERE id=%s AND parent_id=%s",
        (child_id, user["user_id"])
    )
    
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="Not your child")
    
    cur.execute(
        "SELECT id FROM users WHERE id=%s AND role='Doctor'",
        (doctor_id,)
    )
    
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Doctor not found")
    
     # ✅ Prevent duplicate assignment
    cur.execute(
        "SELECT id FROM doctor_children WHERE doctor_id=%s AND child_id=%s",
        (doctor_id, child_id)
    )
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Already assigned")
    # ✅ insert
    cur.execute(
        "INSERT INTO doctor_children(doctor_id, child_id) VALUES (%s, %s) RETURNING id",
        (doctor_id, child_id)
    )
    
    relation = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"msg": "Doctor Assigned", "relation": relation}

@app.post("/next-word")
@app.post("/next-word")
def next_word(data: dict, user=Depends(verify_token)):
    conn = connection()
    cur = conn.cursor()

    child_id = data["child_id"]

    # Check progress
    cur.execute(
        "SELECT current_level, consecutive_failures FROM user_progress WHERE child_id=%s",
        (child_id,)
    )

    progress = cur.fetchone()

    # New child
    if not progress:
        level = "easy"

        cur.execute(
            "INSERT INTO user_progress (child_id, current_level, consecutive_failures) VALUES (%s, %s, %s)",
            (child_id, "easy", 0)
        )

        conn.commit()

    else:
        level, failures = progress

    # Fetch random word
    cur.execute(
        "SELECT id, word, difficulty FROM words WHERE difficulty=%s ORDER BY RANDOM() LIMIT 1",
        (level,)
    )

    word = cur.fetchone()

    if not word:
        raise HTTPException(status_code=404, detail="No words found")

    cur.close()
    conn.close()

    return {
        "word_id": word[0],
        "word": word[1],
        "difficulty": word[2]
    }
    
@app.post("/submit-result")
def submit_result(data: ResultModel, user=Depends(verify_token)):
    conn = connection()
    cur = conn.cursor()
    
    child_id = data.child_id
    word_id = data.word_id
    is_pass = data.is_pass
    score = data.fluency_score
    
    cur.execute(
        "INSERT INTO game_results (child_id, word_id, is_pass, fluency_score) VALUES (%s, %s, %s, %s)",
        (child_id, word_id, is_pass, score)
    )
    
    cur.execute(
        "SELECT current_level, consecutive_failures FROM user_progress WHERE child_id=%s",
        (child_id,)
    )
    progress = cur.fetchone()

    if not progress:
        level = "easy"
        failures = 0

        cur.execute(
            "INSERT INTO user_progress (child_id) VALUES (%s)",
            (child_id,)
        )
        conn.commit()
    else:
        level, failures = progress
    
    if is_pass:
        failures = 0
        if level == "easy":
            level = "medium"
        elif level == "medium":
            level = "hard"
            
    else:
        failures += 1
        if failures >= 3:
            if level == "hard":
                level ="medium"
            elif level == "medium":
                level = "easy"
            failures = 0
            
    cur.execute(
        "UPDATE user_progress SET current_level=%s, consecutive_failures=%s, last_word=%s WHERE child_id=%s",
        (level, failures, word_id, child_id)
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"msg": "Result stored", "new_level": level}

@app.get("/child-progress/{child_id}")
def get_child_progress(child_id: int, user=Depends(verify_token)):
    conn = connection()
    cur = conn.cursor()

    # 🔐 SECURITY → check access
    if user["role"] == "Parent":
        cur.execute(
            "SELECT id FROM children WHERE id=%s AND parent_id=%s",
            (child_id, user["user_id"])
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not your child")

    elif user["role"] == "Doctor":
        cur.execute(
            "SELECT id FROM doctor_children WHERE child_id=%s AND doctor_id=%s",
            (child_id, user["user_id"])
        )
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="Not assigned")

    # 👶 basic progress
    cur.execute(
        "SELECT current_level, consecutive_failures FROM user_progress WHERE child_id=%s",
        (child_id,)
    )
    progress = cur.fetchone()

    if not progress:
        return {"msg": "No data yet"}

    level, failures = progress

    # 📊 stats
    cur.execute(
        """
        SELECT 
            COUNT(*),
            AVG(fluency_score),
            SUM(CASE WHEN is_pass THEN 1 ELSE 0 END)
        FROM game_results
        WHERE child_id=%s
        """,
        (child_id,)
    )

    total, avg_score, passed = cur.fetchone()

    pass_rate = (passed / total * 100) if total else 0

    # 🕒 recent results
    cur.execute(
        """
        SELECT word_id, is_pass, fluency_score, created_at
        FROM game_results
        WHERE child_id=%s
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (child_id,)
    )

    recent = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "current_level": level,
        "failures": failures,
        "total_attempts": total,
        "average_score": float(avg_score) if avg_score else 0,
        "pass_rate": round(pass_rate, 2),
        "recent_activity": [
            {
                "word_id": r[0],
                "is_pass": r[1],
                "score": r[2],
                "time": str(r[3])
            }
            for r in recent
        ]
    }