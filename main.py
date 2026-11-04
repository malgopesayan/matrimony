import os, json, sqlite3, hashlib, secrets, random, time, uuid
from datetime import date
import jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import face

BASE = os.path.dirname(os.path.abspath(__file__))
DB, UP, SECRET = os.path.join(BASE, "matrimony.db"), os.path.join(BASE, "uploads"), "local-dev-secret"
os.makedirs(UP, exist_ok=True)
app = FastAPI(title="MatrimonyConnect (local)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=UP), name="uploads")

def q(sql, args=(), one=False, write=False):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    cur = c.execute(sql, args)
    if write:
        c.commit(); lid = cur.lastrowid; c.close(); return lid
    rows = [dict(r) for r in cur.fetchall()]; c.close()
    return (rows[0] if rows else None) if one else rows

def hp(p, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 100000).hex()

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
    create table if not exists users(id integer primary key, name text, email text unique, phone text unique, pw text,
      gender text, dob text, religion text default '', community text default '', education text default '',
      profession text default '', city text default '', height text default '', about text default '', photo text,
      status text default 'unverified', role text default 'user', otp text, face text, created real);
    create table if not exists prefs(user_id integer primary key, age_min int default 18, age_max int default 45,
      religion text default '', education text default '', city text default '');
    create table if not exists interests(id integer primary key, from_id int, to_id int, status text default 'pending');
    create table if not exists messages(id integer primary key, from_id int, to_id int, body text, ts real);
    create table if not exists reports(id integer primary key, reporter int, target int, reason text, status text default 'open', ts real);
    create table if not exists face_flags(id integer primary key, user_id int, match_id int, status text default 'pending', ts real);
    """)
    if not c.execute("select 1 from users").fetchone():
        def add(n, e, ph, g, dob, rel, com, edu, pro, city, role="user"):
            cur = c.execute("insert into users(name,email,phone,pw,gender,dob,religion,community,education,profession,city,height,about,status,role,created) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (n, e, ph, hp("admin123" if role == "admin" else "demo123"), g, dob, rel, com, edu, pro, city, "5'6\"",
                 "Family-oriented, easy-going and looking for a kind life partner.", "active", role, time.time()))
            c.execute("insert into prefs(user_id) values(?)", (cur.lastrowid,))
        add("Admin", "admin@matri.local", "9000000000", "M", "1990-01-01", "", "", "", "", "", "admin")
        demo = [("Priya Sharma","F","1998-04-12","Hindu","Brahmin","B.Tech","Software Engineer","Pune"),
                ("Anjali Patil","F","1996-09-03","Hindu","Maratha","MBA","Marketing Manager","Mumbai"),
                ("Sana Khan","F","1997-01-21","Muslim","Sunni","MBBS","Doctor","Hyderabad"),
                ("Neha Joshi","F","1999-07-30","Hindu","Brahmin","M.Sc","Teacher","Pune"),
                ("Simran Kaur","F","1995-11-15","Sikh","Jat","B.Com","Chartered Accountant","Delhi"),
                ("Meera Nair","F","1998-02-08","Hindu","Nair","B.Arch","Architect","Bengaluru"),
                ("Rahul Verma","M","1994-05-17","Hindu","Brahmin","B.Tech","Data Scientist","Pune"),
                ("Amit Deshmukh","M","1993-12-02","Hindu","Maratha","MBA","Business Owner","Mumbai"),
                ("Imran Sheikh","M","1995-03-25","Muslim","Sunni","M.Tech","Engineer","Hyderabad"),
                ("Karan Singh","M","1992-08-09","Sikh","Jat","B.Com","Finance Analyst","Delhi"),
                ("Vikram Iyer","M","1996-10-19","Hindu","Iyer","MS","Product Manager","Bengaluru"),
                ("Rohan Kulkarni","M","1997-06-06","Hindu","Brahmin","B.E.","Civil Engineer","Pune")]
        for i, d in enumerate(demo):
            add(d[0], f"{d[0].split()[0].lower()}@demo.com", f"90000010{i:02d}", d[1], d[2], d[3], d[4], d[5], d[6], d[7])
    c.commit(); c.close()
init()

def age(d):
    try:
        b, t = date.fromisoformat(d), date.today()
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    except Exception:
        return None

PUB = ["id", "name", "gender", "dob", "religion", "community", "education", "profession", "city", "height", "about", "photo"]
def pub(u):
    r = {k: u[k] for k in PUB}; r["age"] = age(u["dob"]); return r

def token(uid): return jwt.encode({"id": uid, "exp": time.time() + 7 * 86400}, SECRET, algorithm="HS256")

def me(authorization: str = Header(None)):
    try: uid = jwt.decode(authorization.split()[1], SECRET, algorithms=["HS256"])["id"]
    except Exception: raise HTTPException(401, "Please log in")
    u = q("select * from users where id=?", (uid,), one=True)
    if not u or u["status"] == "suspended": raise HTTPException(401, "Account unavailable")
    return u
def active(u=Depends(me)):
    if u["status"] != "active": raise HTTPException(403, "Your account is under admin review. You'll get access once approved.")
    return u
def admin(u=Depends(me)):
    if u["role"] != "admin": raise HTTPException(403, "Admin only")
    return u

def istat(a, b):
    r = q("select * from interests where (from_id=? and to_id=?) or (from_id=? and to_id=?) order by id desc", (a, b, b, a), one=True)
    if not r: return None
    if r["status"] == "pending": return "sent" if r["from_id"] == a else "received"
    return r["status"]

def score(p, c):
    s = t = 0
    a = age(c["dob"]) or 0
    t += 30; s += 30 if p["age_min"] <= a <= p["age_max"] else 0
    for k, w in (("religion", 30), ("education", 20), ("city", 20)):
        if p[k]: t += w; s += w if p[k].lower() == (c[k] or "").lower() else 0
    return round(100 * s / t)

def candidates(u):
    return q("select * from users where role='user' and status='active' and gender<>? and id<>?", (u["gender"], u["id"]))
@app.get("/")
def home():
    return {
        "status": "success",
        "message": "Matrimony Backend is Running!"
    }
# ---------- auth ----------
@app.post("/api/register")
async def register(name: str = Form(...), email: str = Form(...), phone: str = Form(...), password: str = Form(...),
                   gender: str = Form(...), dob: str = Form(...), face_photo: UploadFile = File(...)):
    email = email.strip().lower()
    if len(password) < 6: raise HTTPException(400, "Password must be at least 6 characters")
    if age(dob) is None or age(dob) < 18: raise HTTPException(400, "You must be 18 or older")
    if q("select 1 from users where email=? or phone=?", (email, phone.strip()), one=True):
        raise HTTPException(400, "Email or phone is already registered")
    emb = face.embed(await face_photo.read())
    if emb is None: raise HTTPException(400, "No clear face found in the photo. Please upload a clear selfie.")
    otp = str(random.randint(100000, 999999))
    uid = q("insert into users(name,email,phone,pw,gender,dob,otp,face,created) values(?,?,?,?,?,?,?,?,?)",
            (name.strip(), email, phone.strip(), hp(password), gender, dob, otp, json.dumps(emb), time.time()), write=True)
    q("insert into prefs(user_id) values(?)", (uid,), write=True)
    for o in q("select id,face from users where id<>? and face is not null and status<>'suspended'", (uid,)):
        if face.same(emb, json.loads(o["face"])):
            q("insert into face_flags(user_id,match_id,ts) values(?,?,?)", (uid, o["id"], time.time()), write=True); break
    return {"phone": phone.strip(), "dev_otp": otp}  # mock SMS: OTP returned for local testing

class Otp(BaseModel): phone: str; otp: str
@app.post("/api/verify-otp")
def verify(b: Otp):
    u = q("select * from users where phone=?", (b.phone,), one=True)
    if not u or u["otp"] != b.otp: raise HTTPException(400, "Incorrect OTP")
    flagged = q("select 1 from face_flags where user_id=? and status='pending'", (u["id"],), one=True)
    q("update users set status=?, otp=null where id=?", ("review" if flagged else "active", u["id"]), write=True)
    return {"token": token(u["id"])}

class Login(BaseModel): login: str; password: str
@app.post("/api/login")
def login(b: Login):
    u = q("select * from users where email=? or phone=?", (b.login.strip().lower(), b.login.strip()), one=True)
    if not u or hp(b.password, u["pw"].split("$")[0]) != u["pw"]: raise HTTPException(400, "Wrong email/phone or password")
    if u["status"] == "suspended": raise HTTPException(403, "This account has been suspended")
    if u["status"] == "unverified":
        u["otp"] = str(random.randint(100000, 999999)); q("update users set otp=? where id=?", (u["otp"], u["id"]), write=True)
        raise HTTPException(403, f"Phone not verified. Mock OTP: {u['otp']} (use Register → verify)")
    return {"token": token(u["id"])}

# ---------- profile ----------
@app.get("/api/me")
def get_me(u=Depends(me)):
    return {**pub(u), "email": u["email"], "phone": u["phone"], "status": u["status"], "role": u["role"],
            "prefs": q("select * from prefs where user_id=?", (u["id"],), one=True)}

class Profile(BaseModel):
    name: str; dob: str; religion: str = ""; community: str = ""; education: str = ""
    profession: str = ""; city: str = ""; height: str = ""; about: str = ""
@app.put("/api/me")
def put_me(b: Profile, u=Depends(me)):
    if age(b.dob) is None or age(b.dob) < 18: raise HTTPException(400, "Invalid date of birth (18+ only)")
    q("update users set name=?,dob=?,religion=?,community=?,education=?,profession=?,city=?,height=?,about=? where id=?",
      (b.name, b.dob, b.religion, b.community, b.education, b.profession, b.city, b.height, b.about, u["id"]), write=True)
    return {"ok": True}

class Prefs(BaseModel): age_min: int = 18; age_max: int = 45; religion: str = ""; education: str = ""; city: str = ""
@app.put("/api/prefs")
def put_prefs(b: Prefs, u=Depends(me)):
    q("update prefs set age_min=?,age_max=?,religion=?,education=?,city=? where user_id=?",
      (b.age_min, b.age_max, b.religion, b.education, b.city, u["id"]), write=True)
    return {"ok": True}

@app.post("/api/me/photo")
async def photo(file: UploadFile = File(...), u=Depends(me)):
    data = await file.read()
    if len(data) > 5_000_000 or not (data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG" or data[:4] == b"RIFF"):
        raise HTTPException(400, "Upload a JPG, PNG or WEBP under 5MB")
    name = uuid.uuid4().hex + ".jpg"
    open(os.path.join(UP, name), "wb").write(data)
    q("update users set photo=? where id=?", ("/uploads/" + name, u["id"]), write=True)
    return {"photo": "/uploads/" + name}

# ---------- discovery ----------
def decorate(u, c, p=None):
    r = pub(c); r["interest"] = istat(u["id"], c["id"])
    if p: r["score"] = score(p, c)
    return r

@app.get("/api/matches")
def matches(u=Depends(active)):
    p = q("select * from prefs where user_id=?", (u["id"],), one=True)
    return sorted([decorate(u, c, p) for c in candidates(u)], key=lambda x: -x["score"])

@app.get("/api/search")
def search(age_min: int = 18, age_max: int = 80, religion: str = "", education: str = "", city: str = "", name: str = "", u=Depends(active)):
    out = []
    for c in candidates(u):
        a = age(c["dob"]) or 0
        if not age_min <= a <= age_max: continue
        if religion and c["religion"].lower() != religion.lower(): continue
        if education and education.lower() not in c["education"].lower(): continue
        if city and city.lower() not in c["city"].lower(): continue
        if name and name.lower() not in c["name"].lower(): continue
        out.append(decorate(u, c))
    return out

@app.get("/api/profile/{uid}")
def profile(uid: int, u=Depends(active)):
    c = q("select * from users where id=? and status='active' and role='user'", (uid,), one=True)
    if not c: raise HTTPException(404, "Profile not found")
    return decorate(u, c)

# ---------- interests ----------
class Send(BaseModel): to_id: int
@app.post("/api/interests")
def send(b: Send, u=Depends(active)):
    t = q("select * from users where id=? and status='active'", (b.to_id,), one=True)
    if not t or t["gender"] == u["gender"] or t["id"] == u["id"]: raise HTTPException(400, "Cannot send interest to this profile")
    s = istat(u["id"], b.to_id)
    if s in ("sent", "accepted", "declined"): raise HTTPException(400, "Interest already " + s)
    if s == "received":
        q("update interests set status='accepted' where from_id=? and to_id=? and status='pending'", (b.to_id, u["id"]), write=True)
        return {"status": "accepted"}
    q("insert into interests(from_id,to_id) values(?,?)", (u["id"], b.to_id), write=True)
    return {"status": "sent"}

@app.get("/api/interests")
def interests(u=Depends(active)):
    out = []
    for i in q("select * from interests where from_id=? or to_id=? order by id desc", (u["id"], u["id"])):
        o = i["to_id"] if i["from_id"] == u["id"] else i["from_id"]
        c = q("select * from users where id=?", (o,), one=True)
        out.append({"id": i["id"], "status": i["status"], "direction": "sent" if i["from_id"] == u["id"] else "received", "user": pub(c)})
    return out

@app.post("/api/interests/{iid}/{action}")
def respond(iid: int, action: str, u=Depends(active)):
    if action not in ("accept", "decline"): raise HTTPException(400, "Bad action")
    i = q("select * from interests where id=? and to_id=? and status='pending'", (iid, u["id"]), one=True)
    if not i: raise HTTPException(404, "Interest not found")
    q("update interests set status=? where id=?", ("accepted" if action == "accept" else "declined", iid), write=True)
    return {"ok": True}

# ---------- chat (accepted matches only) ----------
def chat_ok(u, oid):
    if istat(u["id"], oid) != "accepted": raise HTTPException(403, "Chat opens after an interest is accepted")
@app.get("/api/chats")
def chats(u=Depends(active)):
    return [i["user"] for i in interests(u) if i["status"] == "accepted"]
@app.get("/api/chat/{oid}")
def history(oid: int, u=Depends(active)):
    chat_ok(u, oid)
    return q("select * from messages where (from_id=? and to_id=?) or (from_id=? and to_id=?) order by id", (u["id"], oid, oid, u["id"]))
class Msg(BaseModel): body: str
@app.post("/api/chat/{oid}")
def say(oid: int, b: Msg, u=Depends(active)):
    chat_ok(u, oid)
    if not b.body.strip(): raise HTTPException(400, "Empty message")
    q("insert into messages(from_id,to_id,body,ts) values(?,?,?,?)", (u["id"], oid, b.body.strip()[:1000], time.time()), write=True)
    return {"ok": True}

class Report(BaseModel): target_id: int; reason: str
@app.post("/api/report")
def report(b: Report, u=Depends(active)):
    if not b.reason.strip(): raise HTTPException(400, "Please give a reason")
    q("insert into reports(reporter,target,reason,ts) values(?,?,?,?)", (u["id"], b.target_id, b.reason.strip(), time.time()), write=True)
    return {"ok": True}

# ---------- admin ----------
@app.get("/api/admin/stats")
def stats(a=Depends(admin)):
    n = lambda s: q(s, one=True)["n"]
    return {"users": n("select count(*) n from users where role='user'"), "active": n("select count(*) n from users where status='active' and role='user'"),
            "faces": n("select count(*) n from face_flags where status='pending'"), "reports": n("select count(*) n from reports where status='open'"),
            "interests": n("select count(*) n from interests"), "messages": n("select count(*) n from messages"), "face_mode": face.MODE}
@app.get("/api/admin/users")
def a_users(a=Depends(admin)):
    return [{**pub(x), "email": x["email"], "phone": x["phone"], "status": x["status"]} for x in q("select * from users where role='user' order by id desc")]
class Status(BaseModel): status: str
@app.post("/api/admin/users/{uid}/status")
def a_status(uid: int, b: Status, a=Depends(admin)):
    if b.status not in ("active", "suspended"): raise HTTPException(400, "Bad status")
    q("update users set status=? where id=? and role='user'", (b.status, uid), write=True); return {"ok": True}
@app.get("/api/admin/faces")
def a_faces(a=Depends(admin)):
    out = []
    for f in q("select * from face_flags order by id desc"):
        out.append({**f, "user": pub(q("select * from users where id=?", (f["user_id"],), one=True)),
                    "match": pub(q("select * from users where id=?", (f["match_id"],), one=True))})
    return out
class Decision(BaseModel): decision: str
@app.post("/api/admin/faces/{fid}")
def a_face(fid: int, b: Decision, a=Depends(admin)):
    f = q("select * from face_flags where id=? and status='pending'", (fid,), one=True)
    if not f or b.decision not in ("approve", "reject"): raise HTTPException(400, "Invalid request")
    q("update face_flags set status=? where id=?", ("approved" if b.decision == "approve" else "rejected", fid), write=True)
    q("update users set status=? where id=? and status<>'unverified'", ("active" if b.decision == "approve" else "suspended", f["user_id"]), write=True)
    return {"ok": True}
@app.get("/api/admin/reports")
def a_reports(a=Depends(admin)):
    return [{**r, "reporter": pub(q("select * from users where id=?", (r["reporter"],), one=True))["name"],
             "target_user": pub(q("select * from users where id=?", (r["target"],), one=True))} for r in q("select * from reports order by id desc")]
@app.post("/api/admin/reports/{rid}/{action}")
def a_report(rid: int, action: str, a=Depends(admin)):
    r = q("select * from reports where id=?", (rid,), one=True)
    if not r or action not in ("dismiss", "suspend"): raise HTTPException(400, "Invalid request")
    if action == "suspend": q("update users set status='suspended' where id=? and role='user'", (r["target"],), write=True)
    q("update reports set status=? where id=?", ("dismissed" if action == "dismiss" else "actioned", rid), write=True)
    return {"ok": True}
