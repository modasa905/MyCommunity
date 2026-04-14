import os
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
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

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
    # 정규식을 이용해 --- 와 --- 사이의 텍스트를 찾아냅니다.
    match = re.match(r'^\s*---\n(.*?)\n---\n(.*)', text, re.DOTALL)
    
    if match:
        yaml_text = match.group(1) # 속성 데이터 부분
        body_text = match.group(2).strip() # 진짜 본문
        try:
            metadata = yaml.safe_load(yaml_text) or {}
            return metadata, body_text
        except yaml.YAMLError as e:
            print(f"⚠️ YAML 파싱 에러: {e}")
            return {}, text
            
    # 프런트매터가 아예 없는 파일이라면 빈 딕셔너리와 원본 텍스트를 그대로 반환합니다.
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
# 3. 실행 부분
# ---------------------------------------------------------
if __name__ == "__main__":
    print("지식 베이스 구축을 시작합니다...\n")
    
    print("기존 데이터를 초기화합니다... ")
    supabase.table("obsidian_chunks").delete().neq("id", 0).execute()
    supabase.table("obsidian_documents").delete().neq("id", 0).execute()
    
    all_files = get_all_md_files(OBSIDIAN_VAULT_PATH)
    print(f"총 {len(all_files)}개의 마크다운 파일을 찾았습니다.\n")
    
    total_chunks_inserted = 0
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        clean_title = os.path.splitext(file_name)[0] 
        raw_content = read_md_content(file_path)
        if not raw_content: continue
            
        metadata, pure_content = parse_frontmatter(raw_content)
            
        print(f"[{file_name}] 부모 문서 저장 중... (메타데이터 {len(metadata)}개 발견)")
        
        # 부모 테이블에 저장
        doc_data = {
            "file_name": file_name,
            "full_content": pure_content, # 메타데이터가 제거된 순수 본문만 저장 (또는 raw_content 유지 가능)
            "metadata": metadata          # 추출된 속성값들을 JSON 형태로 저장
        }
        doc_res = supabase.table("obsidian_documents").insert(doc_data).execute()
        document_id = doc_res.data[0]['id']
        
        # 문서를 조각내고, '부모 ID'를 달아서 자식 테이블에 저장
        chunks = chunk_text(pure_content)
        print(f"  ↪ {len(chunks)}개 조각 임베딩 중...")
        
        chunk_records = [] # 조각들을 모아둘 빈 바구니(리스트)를 준비합니다.
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            enriched_chunk = f"[Document: {clean_title} | Part: {i+1} of {len(chunks)}]\n{chunk}"
            vector = get_gemini_embedding(enriched_chunk)
            
            chunk_data = {
                "document_id": document_id, 
                "content": enriched_chunk, 
                "embedding": vector
            }
            # 하나씩 보내지 않고, 일단 바구니에 담습니다.
            chunk_records.append(chunk_data) 
            
        # 바구니에 조각이 모였다면, 단 1번의 API 통신으로 한꺼번에 밀어 넣습니다 (Batch Insert)
        if chunk_records:
            supabase.table("obsidian_chunks").insert(chunk_records).execute()
            total_chunks_inserted += len(chunk_records)
            print(f"  ✅ {len(chunk_records)}개 조각 저장 완료!")
            
    print("\n🎉 모든 작업이 완료되었습니다!")
    print(f"총 {total_chunks_inserted}개의 지식 조각이 부모-자식 구조로 완벽하게 분리 저장되었습니다.")