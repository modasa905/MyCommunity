from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime, timedelta, timezone

# 하이브리드 AI 라이브러리 추가
from google import genai
from google.genai import types
from ollama import Client as OllamaClient
from supabase import create_client, Client as SupabaseClient

app = FastAPI()

# ---------------------------------------------------------
# 1. 환경 변수 및 하이브리드 AI 설정
# ---------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# (1) Supabase 설정 (직접 입력)
SUPABASE_URL = "https://zdthschzdnshnnhtdrbc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkdGhzY2h6ZG5zaG5uaHRkcmJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwNjMwOTgsImV4cCI6MjA5MDYzOTA5OH0.7cyBUlTrU1azmWr-5xKzSCseLplX5oLIeFPOS3YbwJM"
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# (2) Gemini API 설정 (임베딩용 - Render 환경변수 사용)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "여기에_로컬_테스트용_키_입력가능")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# (3) Ollama Cloud API 설정 (대화용 - Render 환경변수 사용)
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "여기에_로컬_테스트용_키_입력가능")
ollama_client = OllamaClient(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
)

CHAT_MODEL = "glm-5.1:cloud" # Ollama Cloud 대화형 모델

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

# ---------------------------------------------------------
# 3. HTML 렌더링 함수
# ---------------------------------------------------------
def render_page(posts, ai_answer="", ai_context="", user_question=""):
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
    
    ai_section = ""
    if ai_answer:
        ai_section = f"""
        <div style="background-color: #f0f7ff; padding: 20px; border-radius: 8px; margin-top: 20px; border-left: 5px solid #2196F3;">
            <h3 style="margin-top: 0; color: #1565C0;">🤖 하이브리드 연구 비서 ({CHAT_MODEL})</h3>
            <p style="color: #555;"><strong>Q: {user_question}</strong></p>
            <p style="white-space: pre-wrap; font-size: 15px; line-height: 1.6;">{ai_answer}</p>
            
            <details style="margin-top: 15px;">
                <summary style="cursor: pointer; color: #888; font-size: 13px;">참고한 내 노트 원문 보기</summary>
                <div style="background-color: #e3f2fd; padding: 10px; border-radius: 5px; margin-top: 10px; font-size: 12px; color: #555; white-space: pre-wrap;">{ai_context}</div>
            </details>
        </div>
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
                <h2 style="margin-top: 0; color: #2196F3;">🔍 내 연구 노트 AI 검색</h2>
                <form action="/ask" method="post" style="display: flex; gap: 10px;">
                    <input type="text" name="question" placeholder="예: Perfect Information의 정의가 뭐야?" required style="flex: 1; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 5px;">
                    <button type="submit" style="padding: 10px 20px; background-color: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">물어보기</button>
                </form>
                {ai_section}
            </div>

            <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h2 style="margin-top: 0; color: #4CAF50;">📝 문의사항 / 방명록</h2>
                <form action="/post" method="post" style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <input type="text" name="content" placeholder="방명록이나 문의사항을 남겨주세요" required style="flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 5px;">
                    <input type="password" name="password" placeholder="비밀번호" required style="width: 100px; padding: 10px; border: 1px solid #ccc; border-radius: 5px;">
                    <button type="submit" style="padding: 10px 20px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">등록</button>
                </form>
                <ul style="list-style-type: none; padding-left: 0;">
                    {posts_list if posts else "<li style='color: gray; text-align: center;'>아직 등록된 문의사항이 없습니다.</li>"}
                </ul>
            </div>
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

@app.post("/ask", response_class=HTMLResponse)
def ask_ai(question: str = Form(...)):
    try:
        # 1. Gemini 임베딩 (3072차원)
        result = gemini_client.models.embed_content(
            model="gemini-embedding-001",
            contents=question,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
        )
        question_embedding = result.embeddings[0].values
        
        # 2. Supabase 검색
        response = supabase.rpc("match_notes", {
            "query_embedding": question_embedding,
            "match_threshold": 0.3, 
            "match_count": 3
        }).execute()
        
        retrieved_docs = response.data
        context_text = ""
        if retrieved_docs:
            for i, doc in enumerate(retrieved_docs):
                context_text += f"[참고 {i+1}] {doc['content']}\n\n"

        ai_response = ollama_client.chat(model=CHAT_MODEL, messages=[
            {"role": "system", "content": f"낙준의 비서입니다. 참고: {context_text}"},
            {"role": "user", "content": question}
        ])
        answer = ai_response['message']['content']

    except Exception as e:
        # 💡 여기가 핵심입니다! 에러가 나면 브라우저 화면에 에러 내용을 직접 뿌립니다.
        import traceback
        error_details = traceback.format_exc()
        print(f"🚨 에러 발생: {error_details}")
        answer = f"AI 엔진 에러 발생!\n내용: {str(e)}\n\n모델명 '{CHAT_MODEL}'이 올바른 모델 이름인지 확인해 주세요."
        context_text = "상세 에러 로그:\n" + error_details

    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    db.close()
    
    return render_page(posts, ai_answer=answer, ai_context=context_text, user_question=question)

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