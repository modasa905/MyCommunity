import os
import shutil
import re
import yaml
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

# ---------------------------------------------------------
# 🛠️ 1. 환경 설정
# ---------------------------------------------------------
load_dotenv()
STAGE_FOLDER_PATH = os.getenv("STAGE_FOLDER_PATH")
TARGET_FOLDER_PATH = os.getenv("OBSIDIAN_VAULT_PATH")

# Supabase 세팅
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini 세팅
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# 모델 설정
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

# ---------------------------------------------------------
# 🧠 2. 핵심 함수들
# ---------------------------------------------------------
def get_all_md_files(directory_path):
    md_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                md_files.append(os.path.join(root, file))
    return md_files

def read_md_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"🚨 파일 읽기 에러 ({file_path}): {e}")
        return None

def parse_frontmatter(text):
    match = re.match(r'^\s*---\n(.*?)\n---\n(.*)', text, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body_text = match.group(2).strip()
        try:
            metadata = yaml.safe_load(yaml_text) or {}
            return metadata, body_text
        except yaml.YAMLError as e:
            print(f"⚠️ YAML 파싱 에러: {e}")
            return {}, text
    return {}, text

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def get_gemini_embedding(text):
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
    )
    return result.embeddings[0].values

# ---------------------------------------------------------
# 3. 실행 부분 (메타데이터 + 부모-자식 구조 + Batching + 파일 이동)
# ---------------------------------------------------------
if __name__ == "__main__":
    print(f"🔍 Stage 폴더의 파일 동기화를 시작합니다...\n")
    
    stage_files = get_all_md_files(STAGE_FOLDER_PATH)
    
    if not stage_files:
        print("⚠️ Stage 폴더에 처리할 마크다운 파일이 없습니다.")
        exit()
        
    print(f"📂 총 {len(stage_files)}개의 타겟 파일을 발견했습니다.\n")
    
    total_chunks_inserted = 0
    for file_path in stage_files:
        file_name = os.path.basename(file_path)
        clean_title = os.path.splitext(file_name)[0] 
        
        # 1. DB의 기존 데이터 삭제 (부모만 지우면 자식은 폭파됩니다 - CASCADE 마법)
        print(f"🧹 [{file_name}] 기존 데이터가 있다면 삭제 중...")
        supabase.table("obsidian_documents").delete().eq("file_name", file_name).execute()
        
        raw_content = read_md_content(file_path)
        if not raw_content: continue
            
        # 2. 메타데이터와 순수 본문 분리
        metadata, pure_content = parse_frontmatter(raw_content)
        
        # 3. 부모 테이블에 저장 후 ID 발급
        doc_data = {
            "file_name": file_name,
            "full_content": pure_content,
            "metadata": metadata
        }
        doc_res = supabase.table("obsidian_documents").insert(doc_data).execute()
        document_id = doc_res.data[0]['id']
            
        chunks = chunk_text(pure_content)
        print(f"⏳ [{file_name}] 새 데이터 임베딩 중... ({len(chunks)}개 조각)")
        
        # 4. 자식 조각들을 바구니에 담기 (Batch Insert 준비)
        chunk_records = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            enriched_chunk = f"[Document: {clean_title} | Part: {i+1} of {len(chunks)}]\n{chunk}"
            vector = get_gemini_embedding(enriched_chunk)
            
            chunk_records.append({
                "document_id": document_id, 
                "content": enriched_chunk, 
                "embedding": vector
            })
            
        # 5. 바구니에 담긴 조각들을 한 번의 통신으로 쏟아붓기
        if chunk_records:
            supabase.table("obsidian_chunks").insert(chunk_records).execute()
            total_chunks_inserted += len(chunk_records)
            
        # 6. 파일 이동 (작업 완료 후 본래 폴더로 복귀)
        target_path = os.path.join(TARGET_FOLDER_PATH, file_name)
        shutil.move(file_path, target_path) 
        print(f"📦 [{file_name}] 메타데이터 추출 완료 & 파일 본래 위치로 이동 성공!\n")
            
    print("🎉 Stage 폴더 동기화 및 파일 정리가 완벽하게 완료되었습니다!")
    print(f"📚 DB에 새롭게 덮어씌워진 지식 조각: {total_chunks_inserted}개")