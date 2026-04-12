from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from datetime import datetime, timedelta, timezone
import traceback
from dotenv import load_dotenv
import random

# AI 라이브러리
from google import genai
from google.genai import types
from ollama import Client as OllamaClient
from supabase import create_client, Client as SupabaseClient

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------
# 1. 환경 변수 및 하이브리드 AI 설정
# ---------------------------------------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
ollama_client = OllamaClient(
    host="https://ollama.com",
    headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
)

CRON_SECRET = os.getenv("CRON_SECRET") 

CHAT_MODEL = "glm-5.1:cloud"
DRAFT_MODEL = "gemini-3.1-flash-lite-preview"

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

class DraftNote(Base):
    __tablename__ = "draft_notes"
    id = Column(Integer, primary_key=True, index=True)
    source_file = Column(String) # 영감을 준 원본 파일명
    content = Column(String)     # AI가 새로 작성한 내용
    created_at = Column(String, default=get_kst_now)

Base.metadata.create_all(bind=engine)

class SearchRequest(BaseModel):
    question: str

class GenerateRequest(BaseModel):
    question: str
    context: str

# ---------------------------------------------------------
# 3. 라우터 설정
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    db = SessionLocal()
    posts = db.query(Post).order_by(Post.id.desc()).all()
    drafts = db.query(DraftNote).order_by(DraftNote.id.desc()).all()
    db.close()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
        "posts": posts,
        "drafts": drafts
        }
    )

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
        
        raw_answer = ai_response['message']['content']
        return {"answer": raw_answer}
    
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"🚨 생성 에러: {error_msg}")
        return {"error": str(e)}

CRON_SECRET = os.getenv("CRON_SECRET") 

@app.get("/api/generate-daily-draft")
async def generate_daily_draft(secret: str = ""):
    # 1. 보안 검증
    if secret != CRON_SECRET:
        return JSONResponse(status_code=401, content={"error": "접근 권한이 없습니다."})

    try:
        # 2. Supabase에서 랜덤으로 노트 하나 뽑기
        response = supabase.table("obsidian_notes").select("*").execute()
        if not response.data:
            return {"status": "error", "message": "도서관에 책이 없습니다."}
        
        random_doc = random.choice(response.data)
        
        prompt = f"""You are an expert research assistant specializing in advanced economics and mathematics.
        Based on the concepts in the [Original Note] below, generate a new document that explores advanced mathematical/economic applications, theoretical extensions, or novel academic insights.
        
        The output MUST be written entirely in professional, academic English.
        You MUST strictly follow the exact structure below. Do not add any conversational filler.

        [Part 1]
        Title: (Provide a descriptive filename, e.g., Advanced_Optimal_Taxation.md)
        Explanation: (Briefly explain the core idea of this new note in plain text. Do NOT use markdown format here.)



        [Part 2]
        (Write the complete document here. This section must be written in pure Markdown format, ready to be added directly to a database. Use appropriate headers, and LaTeX for math enclosed in $ or $$. Do NOT wrap this section in ```markdown code blocks.)
        
        ***
        (Append a metadata section (Parent Path, Sequence, Related Notes, and Source) that exactly mirrors the formatting of the [Original Note]. Thoughtfully adapt the links to fit this new extension.)
        
        [Original Note: {random_doc['file_name']}]
        {random_doc['content']}
        """
        
        ai_response = gemini_client.models.generate_content(
            model=DRAFT_MODEL,
            contents=prompt
        )
        
        full_content = ""
        if ai_response.candidates and ai_response.candidates[0].content.parts:
            for part in ai_response.candidates[0].content.parts:
                if part.text:
                    full_content += part.text
        
        # 4. 작성된 글을 임시 보관함(DraftNote)에 저장
        db = SessionLocal()
        new_draft = DraftNote(
            source_file=random_doc['file_name'],
            content=full_content
        )
        db.add(new_draft)
        db.commit()
        db.close()
        
        return RedirectResponse(url="/", status_code=303)
    
    except Exception as e:
        print(f"🚨 새벽 자동화 에러: {e}")
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