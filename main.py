from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

app = FastAPI()

# 1. 환경 변수에서 Supabase 주소를 가져옵니다.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Render 설정에 'DATABASE_URL'이 없습니다! Environment 탭을 확인해주세요.")

# 2. SQLite용 특별 옵션을 빼고, 정석대로 DB 엔진을 만듭니다.
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)

Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def read_root():
    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    db.close()
    
    posts_list = "".join([f"<li>{p.content}</li>" for p in posts])
    
    html_content = f"""
    <html>
        <head><meta charset="utf-8"><title>낙준의 Supabase 게시판</title></head>
        <body>
            <h1>낙준 게시판</h1>
            <form action="/post" method="post">
                <input type="text" name="content" placeholder="내용을 입력하세요" required>
                <button type="submit">등록</button>
            </form>
            <hr>
            <ul>
                {posts_list if posts else "<li>아직 저장된 글이 없습니다.</li>"}
            </ul>
        </body>
    </html>
    """
    return html_content

@app.post("/post")
def create_post(content: str = Form(...)):
    db = SessionLocal()
    new_post = Post(content=content)
    db.add(new_post)
    db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)