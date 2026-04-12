from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timedelta, timezone
import traceback

# AI 라이브러리
from google import genai
from google.genai import types
from ollama import Client as OllamaClient
from supabase import create_client, Client as SupabaseClient

app = FastAPI()

# ---------------------------------------------------------
# 1. 환경 변수 및 하이브리드 AI 설정
# ---------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

SUPABASE_URL = "https://zdthschzdnshnnhtdrbc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkdGhzY2h6ZG5zaG5uaHRkcmJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwNjMwOTgsImV4cCI6MjA5MDYzOTA5OH0.7cyBUlTrU1azmWr-5xKzSCseLplX5oLIeFPOS3YbwJM"
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "여기에_로컬_테스트용_키_입력가능")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "여기에_로컬_테스트용_키_입력가능")
ollama_client = OllamaClient(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
)

CHAT_MODEL = "glm-5.1:cloud"

# ---------------------------------------------------------
# 2. 방명록 DB 설정
# ---------------------------------------------------------
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

class SearchRequest(BaseModel):
    question: str

class GenerateRequest(BaseModel):
    question: str
    context: str

# ---------------------------------------------------------
# 3. HTML 렌더링
# ---------------------------------------------------------
def render_page(posts):
    posts_list = ""
    for p in posts:
        posts_list += f"""
        <li style="margin-bottom: 15px; padding: 10px; background: #fff; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <span style="color: gray; font-size: 13px; margin-right: 10px;">[{p.created_at}]</span>
            <span style="font-size: 16px;">{p.content}</span>
            <form action="/delete/{p.id}" method="post" style="display:inline; float:right;">
                <input type="password" name="password" placeholder="비밀번호" required style="width: 70px; padding: 2px;">
                <button type="submit" style="color:white; background-color:#ff4d4d; border:none; border-radius:3px; padding: 3px 6px; cursor:pointer;">삭제</button>
            </form>
        </li>
        """
    
    return f"""
    <html>
        <head>
            <meta charset="utf-8">
            <title>낙준의 연구 & 문의 게시판</title>
            <style>body {{ max-width: 800px; margin: 0 auto; padding: 20px; font-family: 'Apple SD Gothic Neo', sans-serif; background-color: #fafafa; }}</style>
        </head>
        <body>
            <h1 style="text-align: center; color: #333;">낙준의 개인 지식 베이스</h1>
            
            <div style="background: white; border: 2px solid #2196F3; padding: 20px; border-radius: 8px; margin-bottom: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h2 style="margin-top: 0; color: #2196F3;">내 연구 노트 내 검색</h2>
                <form id="askForm" onsubmit="askAI(event)" style="display: flex; gap: 10px;">
                    <input type="text" id="questionInput" placeholder="" required style="flex: 1; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 5px;">
                    <button type="submit" id="askBtn" style="padding: 10px 20px; background-color: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">검색</button>
                </form>

                <div id="ai-result-area" style="display: none; background-color: #f0f7ff; paddiing 20px; border-radius: 8px; margin-top: 20px; border-left: 5px solid #2196F3;">
                </div>
            </div>

            <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h2 style="margin-top: 0; color: #4CAF50;"> 문의사항 </h2>
                <form action="/post" method="post" style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <input type="text" name="content" placeholder="문의사항을 남겨주세요" required style="flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px;">
                    <input type="password" name="password" placeholder="비밀번호" required style="width: 100px; padding: 10px; border: 1px solid #ccc; border-radius: 5px;">
                    <button type="submit" style="padding: 10px 20px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">등록</button>
                </form>
                <ul style="list-style-type: none; padding-left: 0;">
                    {posts_list if posts else "<li style='color: gray; text-align: center;'>아직 등록된 문의사항이 없습니다.</li>"}
                </ul>
            </div>

            <script>
            async function askAI(event) {{
                event.preventDefault();
                
                const question = document.getElementById('questionInput').value;
                const resultArea = document.getElementById('ai-result-area');
                const askBtn = document.getElementById('askBtn');
                
                // 검색 시작 전 UI 초기화
                askBtn.disabled = true;
                askBtn.style.backgroundColor = 'gray';
                resultArea.style.display = 'block';
                resultArea.innerHTML = `
                    <h3 style="margin-top: 0; color: #1565C0;">🔍 질문: ${{question}}</h3>
                    <p style="color: #666; font-weight: bold;">⚡ Gemini API로 관련 노트를 빠르게 찾는 중...</p>
                `;

                try {{
                    // [STEP 1] 빠른 검색 (Gemini + Supabase)
                    const searchRes = await fetch('/api/search', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ question: question }})
                    }});
                    const searchData = await searchRes.json();

                    if (!searchData.docs || searchData.docs.length === 0) {{
                        resultArea.innerHTML += `<p style="color: red;">관련된 노트를 찾을 수 없습니다.</p>`;
                        askBtn.disabled = false;
                        askBtn.style.backgroundColor = '#2196F3';
                        return;
                    }}

                    // 검색된 문서 화면에 먼저 보여주기
                    let contextText = "";
                    let docsHtml = `<div style="background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin-top: 10px; font-size: 13px;"><strong>📚 참고할 노트 발견 완료!</strong><ul>`;
                    searchData.docs.forEach((doc, idx) => {{
                        docsHtml += `<li>${{doc.file_name}}</li>`;
                        contextText += `[참고문헌 ${{idx+1}} - ${{doc.file_name}}]\\n${{doc.content}}\\n\\n`;
                    }});
                    docsHtml += `</ul></div>`;
                    
                    resultArea.innerHTML += docsHtml;
                    resultArea.innerHTML += `<p id="ai-loading" style="color: #E65100; font-weight: bold; margin-top: 15px;">🐌 Ollama Cloud가 답변을 꼼꼼히 작성 중입니다. 잠시만 기다려주세요...</p>`;

                    // [STEP 2] 느린 답변 생성 (Ollama Cloud)
                    const genRes = await fetch('/api/generate', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ question: question, context: contextText }})
                    }});
                    const genData = await genRes.json();

                    // 로딩 문구 지우고 최종 답변 표시
                    document.getElementById('ai-loading').style.display = 'none';
                    if (genData.error) {{
                        resultArea.innerHTML += `<p style="color: red; margin-top: 15px;">에러: ${{genData.error}}</p>`;
                    }} else {{
                        resultArea.innerHTML += `<p style="white-space: pre-wrap; font-size: 15px; line-height: 1.6; margin-top: 15px; border-top: 1px dashed #ccc; padding-top: 15px;">${{genData.answer}}</p>`;
                    }}

                }} catch (error) {{
                    resultArea.innerHTML += `<p style="color: red;">통신 중 에러가 발생했습니다: ${{error.message}}</p>`;
                }} finally {{
                    // 버튼 원상복구
                    askBtn.disabled = false;
                    askBtn.style.backgroundColor = '#2196F3';
                }}
            }}
            </script>
        </body>
    </html>
    """

# ---------------------------------------------------------
# 4. 라우터 설정
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def read_root():
    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    db.close()
    return render_page(posts)

# [API 1] 검색 전용 엔드포인트 (빠름)
@app.post("/api/search")
async def api_search(request: SearchRequest):
    try:
        # Gemini 3072차원 임베딩
        result = gemini_client.models.embed_content(
            model="gemini-embedding-001",
            contents=request.question,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        question_embedding = result.embeddings[0].values
        
        # Supabase 검색
        response = supabase.rpc("match_notes", {
            "query_embedding": question_embedding,
            "match_threshold": 0.3, 
            "match_count": 3
        }).execute()
        
        return {"docs": response.data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# [API 2] 답변 생성 전용 엔드포인트 (느림)
@app.post("/api/generate")
async def api_generate(request: GenerateRequest):
    try:
        system_prompt = f"당신은 경제학 연구자의 비서입니다. 아래 [참고문헌]을 바탕으로 한국어로 답하세요.\n\n[참고문헌]\n{request.context}"
        
        ai_response = ollama_client.chat(model=CHAT_MODEL, messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.question}
        ])
        
        return {"answer": ai_response['message']['content']}
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"🚨 생성 에러: {error_msg}")
        return {"error": str(e)}
    
@app.post("/post")
def create_post(content: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    new_post = Post(content=content, password=password)
    db.add(new_post)
    db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{post_id}")
def delete_post(post_id: int, password: str = Form(...)):
    db = SessionLocal()
    post_to_delete = db.query(Post).filter(Post.id == post_id).first()
    if post_to_delete and post_to_delete.password == password:
        db.delete(post_to_delete)
        db.commit()
    db.close()
    return RedirectResponse(url="/", status_code=303)