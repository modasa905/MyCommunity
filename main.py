from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import sqlite3 # [추가] 파이썬 기본 내장 DB 도구

app = FastAPI()
DB_NAME = "community.db"

# [추가] 처음 실행할 때 DB와 테이블(표)을 만드는 함수
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 'posts'라는 이름의 표를 만듭니다. (id 번호와 content 내용 칸)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db() # 서버 켤 때 실행

@app.get("/", response_class=HTMLResponse)
def read_root():
    # DB에서 글 목록 가져오기
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM posts ORDER BY id DESC") # 최신글부터 가져오기
    db_posts = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    posts_list = "".join([f"<li>{post}</li>" for post in db_posts])
    
    html_content = f"""
    <html>
        <head><meta charset="utf-8"><title>낙준의 DB 게시판</title></head>
        <body>
            <h1>진짜 DB 게시판 (3차 목표)</h1>
            <form action="/post" method="post">
                <input type="text" name="content" placeholder="내용을 입력하세요" required>
                <button type="submit">등록</button>
            </form>
            <hr>
            <ul>
                {posts_list if db_posts else "<li>아직 저장된 글이 없습니다.</li>"}
            </ul>
        </body>
    </html>
    """
    return html_content

@app.post("/post")
def create_post(content: str = Form(...)):
    # DB에 글 저장하기
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO posts (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()
    return HTMLResponse(content="<script>window.location.href='/';</script>")