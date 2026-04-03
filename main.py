from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timedelta, timezone

app = FastAPI()

# 환경 변수에서 Supabase 주소를 가져오기
DATABASE_URL = os.getenv("DATABASE_URL")

# DB 엔진 만들기
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# KST 구하는 함수 만들기
KST = timezone(timedelta(hours=9))
def get_kst_now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    password = Column(String)
    created_at = Column(String, default=get_kst_now)

Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def read_root():
    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    db.close()
    
    posts_list = ""
    for p in posts:
            posts_list += f"""
            <li style="margin-bottom: 15px;">
                <span style="color: gray; font-size: 13px; margin-right: 10px;">[{p.created_at}]</span>
                <span style="font-size: 16px;">{p.content}</span>
                <form action="/delete/{p.id}" method="post" style="display:inline; margin-left:10px;">
                    <input type="password" name="password" placeholder="삭제 비밀번호" required style="width: 90px; padding: 2px;">
                    <button type="submit" style="color:white; background-color:red; border:none; border-radius:3px; padding: 3px 6px; cursor:pointer;">지우기</button>
                </form>
            </li>
            """
   
    html_content = f"""
    <html>
        <head><meta charset="utf-8"><title>낙준의 게시판</title></head>
        <body>
            <h1>낙준의 게시판에 오신 것을 환영합니다!</h1>
            <form action="/post" method="post" style="margin-bottom: 20px;">
                <input type="text" name="content" placeholder="내용을 입력하세요" required style="padding: 5px; width: 200px;">
                <input type="password" name="password" placeholder="비밀번호 설정" required style="padding: 5px; width: 100px;">
                <button type="submit" style="padding: 5px 15px;">등록</button>
            </form>
            <hr>
            <ul style="list-style-type: square;">
                {posts_list if posts else "<li>아직 저장된 글이 없습니다.</li>"}
            </ul>
        </body>
    </html>
    """
    return html_content

@app.post("/post")
def create_post(content: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    new_post = Post(content=content, password=password)
    db.add(new_post)
    db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

# 특정 ID의 글을 찾아서 삭제하는 기능
@app.post("/delete/{post_id}")
def delete_post(post_id: int, password: str = Form(...)):
    db = SessionLocal()
    post_to_delete = db.query(Post).filter(Post.id == post_id).first()
    
    if post_to_delete and post_to_delete.password == password:
        db.delete(post_to_delete)
        db.commit()
        
    db.close()
    return RedirectResponse(url="/", status_code=303)