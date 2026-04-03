from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

app = FastAPI()

# 1. 환경 변수에서 Supabase 주소를 가져옵니다.
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. DB 엔진을 만듭니다.
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
    
    posts_list = ""
    for p in posts:
            posts_list += f"""
            <li style="margin-bottom: 5px;">
                {p.content}
                <form action="/delete/{p.id}" method="post" style="display:inline; margin-left:10px;">
                    <button type="submit" style="color:red; font-size:12px; cursor:pointer;">지우기</button>
                </form>
            </li>
            """
   
    html_content = f"""
    <html>
        <head><meta charset="utf-8"><title>낙준의 게시판</title></head>
        <body>
            <h1>낙준의 게시판에 오신 것을 환영합니다!</h1>
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

# 특정 ID의 글을 찾아서 삭제하는 기능
@app.post("/delete/{post_id}")
def delete_post(post_id: int):
    db = SessionLocal()
    # 1. DB에서 post_id 번호와 일치하는 글을 찾습니다.
    post_to_delete = db.query(Post).filter(Post.id == post_id).first()
    
    # 2. 글이 존재한다면 삭제(delete)하고 저장(commit)합니다.
    if post_to_delete:
        db.delete(post_to_delete)
        db.commit()
        
    db.close()
    # 3. 메인 화면으로 돌아갑니다.
    return RedirectResponse(url="/", status_code=303)