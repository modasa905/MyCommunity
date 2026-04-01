from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import os

app = FastAPI()

# 저장할 파일 이름
DB_FILE = "posts.txt"

# [추가] 파일에서 글을 읽어오는 함수
def load_posts():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r", encoding="utf-8") as f:
        # 파일의 각 줄을 읽어서 리스트로 만듭니다.
        return [line.strip() for line in f.readlines()]

# [추가] 파일에 글을 저장하는 함수
def save_post(content):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        # 글 끝에 줄바꿈(\n)을 붙여서 파일 끝에 추가(append)합니다.
        f.write(content + "\n")

@app.get("/", response_class=HTMLResponse)
def read_root():
    # 이제 리스트가 아니라 파일에서 글을 가져옵니다.
    db_posts = load_posts()
    
    posts_list = "".join([f"<li>{post}</li>" for post in db_posts])
    
    html_content = f"""
    <html>
        <head><meta charset="utf-8"><title>낙준의 저장되는 커뮤니티</title></head>
        <body>
            <h1>영구 저장 게시판 (2차 목표)</h1>
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
    # 리스트에 넣는 대신 파일에 저장합니다.
    save_post(content)
    return HTMLResponse(content="<script>window.location.href='/';</script>")