import os
import re
import yaml
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# ---------------------------------------------------------
# 1. 환경 설정
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
# 2. 핵심 함수들
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
    
    # 3. LangChain 하이브리드 분할기 초기 세팅
    # 헤더 레벨 지정 (여기 등록된 헤더들은 잘리지 않고 메타데이터로 보존됩니다)
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, 
        strip_headers=False # 원문 헤더를 삭제하지 않고 유지
    )
    # 1,000자로 맞추되, 수식이나 문장이 최대한 안 깨지도록 분리기호 순서 지정
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " ", ""] 
    )
    
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
        
        doc_data = {
            "file_name": file_name,
            "full_content": pure_content, 
            "metadata": metadata          
        }
        doc_res = supabase.table("obsidian_documents").insert(doc_data).execute()
        document_id = doc_res.data[0]['id']
        
        # 4. 새로운 하이브리드 청크 분할 적용!
        # 1차: 마크다운 헤더 구조를 파악하며 분할
        md_header_splits = markdown_splitter.split_text(pure_content)
        # 2차: 헤더로 나뉜 덩어리가 1000자가 넘으면 안전하게 글자 수/문단 기준으로 재분할
        final_chunks = text_splitter.split_documents(md_header_splits)
        
        print(f"  ↪ {len(final_chunks)}개 조각 임베딩 중...")
        
        chunk_records = [] 
        
        for i, chunk_doc in enumerate(final_chunks):
            chunk_text = chunk_doc.page_content # LangChain 객체에서 실제 텍스트 추출
            if not chunk_text.strip(): continue
            
            # 5. 조각의 '이름표'를 아주 똑똑하게 달아줍니다!
            # LangChain이 저장해둔 헤더 메타데이터를 가져와 "1. 최적조세 > 수식 도출" 형태로 만듭니다.
            header_info = " > ".join([v for k, v in chunk_doc.metadata.items() if k.startswith("Header")])
            header_context = f" | Section: {header_info}" if header_info else ""
            
            # 예: [Document: Saez(2001) | Section: 2. Mathematical Model > 2.1 Derivation | Part: 3 of 5]
            enriched_chunk = f"[Document: {clean_title}{header_context} | Part: {i+1} of {len(final_chunks)}]\n{chunk_text}"
            
            vector = get_gemini_embedding(enriched_chunk)
            
            chunk_data = {
                "document_id": document_id, 
                "content": enriched_chunk, 
                "embedding": vector
            }
            chunk_records.append(chunk_data) 
            
        if chunk_records:
            supabase.table("obsidian_chunks").insert(chunk_records).execute()
            total_chunks_inserted += len(chunk_records)
            print(f"  ✅ {len(chunk_records)}개 조각 저장 완료!")
            
    print("\n🎉 모든 작업이 완료되었습니다!")
    print(f"총 {total_chunks_inserted}개의 지식 조각이 구조를 유지한 채 분리 저장되었습니다.")