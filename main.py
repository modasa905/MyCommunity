from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI()

# 1. 데이터를 담을 바구니 (서버를 끄면 초기화되지만, 연습용으로 최고!)
db_posts = []

@app.get("/", response_class=HTMLResponse)
def read_root():
    # 2. 저장된 글들을 하나씩 리스트 아이템(<li>)으로 만듭니다.
    posts_list = "".join([f"<li>{post}</li>" for post in db_posts])
    
    # 3. 브라우저에 뿌려줄 HTML 화면 설계
    html_content = f"""
    <html>
        <head>
            <meta charset="utf-8">
            <title>낙준의 커뮤니티</title>
        </head>
        <body>
            <h1>나만의 익명 게시판</h1>
                        
            <form action="/post" method="post">
                <input type="text" name="content" placeholder="내용을 입력하세요" required>
                <button type="submit">등록</button>
            </form>
            
            <hr>
            <h3>전체 글 목록</h3>
            <ul>
                {posts_list if db_posts else "<li>아직 작성된 글이 없습니다.</li>"}
            </ul>
        </body>
    </html>
    """
    return html_content

@app.post("/post")
def create_post(content: str = Form(...)):
    # 4. 사용자가 보낸 content를 리스트에 추가합니다.
    db_posts.append(content)
    
    # 5. 글을 다 썼으면 다시 메인 페이지('/')로 돌아가게 합니다.
    return HTMLResponse(content="<script>window.location.href='/';</script>")