from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# [수정] 다시 파일 저장 방식(SQLite)으로 돌아갑니다. 환경변수 필요 없음!
DATABASE_URL = "sqlite:///./community.db"

# SQLite를 쓸 때 필요한 특별 설정입니다.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
        <head><meta charset="utf-8"><title>낙준의 게시판 (로컬 저장)</title></head>
        <body>
            <h1>게시판 (SQLite)</h1>
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