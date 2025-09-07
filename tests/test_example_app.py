# app.py
import os, io, re, time, logging
from typing import List, Dict, Set, Tuple, Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import pdfplumber

import streamlit as st
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain.prompts import ChatPromptTemplate

# ==== NEW: BM25 ====
from rank_bm25 import BM25Okapi

# ---------- Конфиг ----------
load_dotenv()
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_SEEDS = [
    "https://abit.itmo.ru/program/master/ai",
    "https://abit.itmo.ru/program/master/ai_product",
]
USER_AGENT = "Mozilla/5.0 (compatible; itmo-rag-mvp/1.0)"
REQUEST_TIMEOUT = 20
CRAWL_DELAY_SEC = 0.2
MAX_PAGES = 40
MAX_DEPTH = 1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-mvp")

# ---------- Парсинг ----------
# Скрытие think
THINK_PATTERNS = [
    (re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE), "xml"),
    (re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL | re.IGNORECASE), "xml2"),
    (re.compile(r"```(?:think|reasoning)?\s*(.*?)```", re.DOTALL | re.IGNORECASE), "fence"),
]

def split_think(s: str) -> tuple[str, str | None]:
    if not s:
        return s, None
    hidden = []
    main = s
    for pat, _ in THINK_PATTERNS:
        for m in pat.finditer(main):
            hidden.append(m.group(1).strip())
        main = pat.sub("", main)
    main = main.strip()
    think_text = "\n\n---\n\n".join(hidden).strip() if hidden else None
    return main, think_text

def clean_text(s: str) -> str:
    s = (s or "").replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def safe_get(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200: return r
        logger.warning("GET %s -> %s", url, r.status_code)
    except Exception as e:
        logger.warning("GET %s error: %s", url, e)
    return None

def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("main") or soup.select_one("article") or soup.body or soup
    return clean_text(root.get_text("\n", strip=True))

def _uniq(xs: List[str]) -> List[str]:
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def is_curriculum_anchor(a) -> bool:
    t = (a.get_text(" ", strip=True) or "").lower()
    return any(k in t for k in ["учебн", "план", "curriculum", "syllabus"])

def extract_links(html: str, base_url: str, allowed_domains: Set[str]) -> Tuple[List[str], List[str]]:
    soup = BeautifulSoup(html, "lxml")
    html_links, pdf_links = [], []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)
        p = urlparse(full)
        if p.scheme not in ("http", "https"): continue
        if p.netloc not in allowed_domains: continue
        if full.lower().endswith(".pdf"):
            pdf_links.append(full)
        else:
            (pdf_links if is_curriculum_anchor(a) else html_links).append(full)
    return _uniq(html_links), _uniq(pdf_links)

def parse_pdf_bytes_with_plumber(data: bytes) -> str:
    with io.BytesIO(data) as bio:
        try:
            with pdfplumber.open(bio) as pdf:
                texts = []
                for page in pdf.pages:
                    try: txt = page.extract_text() or ""
                    except Exception: txt = ""
                    if txt: texts.append(txt)
                return clean_text("\n".join(texts))
        except Exception as e:
            logger.warning("pdfplumber open error: %s", e)
            return ""

# ==== NEW: токенизация для BM25 ====
WORD_RE = re.compile(r"\w+", re.UNICODE)
def tokenize(s: str) -> List[str]:
    return [w.casefold() for w in WORD_RE.findall(s or "")]

# ---------- Краулер с прогрессом ----------
def crawl(
    seeds: List[str],
    max_pages: int = MAX_PAGES,
    max_depth: int = MAX_DEPTH,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> Dict[str, Dict]:
    # домены для грубой отсечки внутри extract_links
    allowed_domains = {urlparse(u).netloc for u in seeds}

    # строгие префиксы путей: только подпути seed-ов
    def _norm_prefix(u: str) -> str:
        p = urlparse(u)
        base = f"{p.scheme}://{p.netloc}{p.path}"
        if not base.endswith("/"):
            base += "/"
        return base

    allowed_prefixes = [_norm_prefix(u) for u in seeds]

    def _in_allowed_prefix(u: str) -> bool:
        # сравниваем без query/fragment
        p = urlparse(u)
        no_q = f"{p.scheme}://{p.netloc}{p.path}"
        if not no_q.endswith("/"):
            # чтобы корректно матчить файлы (pdf) и страницы
            no_q_slash = no_q + "/"
        else:
            no_q_slash = no_q
        return any(no_q.startswith(pref) or no_q_slash.startswith(pref) for pref in allowed_prefixes)

    queue: List[Tuple[str, int]] = [(u, 0) for u in seeds]
    seen: Set[str] = set()
    out: Dict[str, Dict] = {}
    fetched = 0

    while queue and fetched < max_pages:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)

        # жёсткая отсечка всего, что не подпуть seed-ов
        if not _in_allowed_prefix(url):
            if on_progress:
                on_progress(f"SKIP (out of scope) {url}", fetched, max_pages)
            continue

        if on_progress:
            on_progress(f"GET {url}", fetched, max_pages)
        r = safe_get(url)
        if not r:
            if on_progress:
                on_progress(f"SKIP {url}", fetched, max_pages)
            continue

        ctype = (r.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            text = parse_pdf_bytes_with_plumber(r.content)
            if text:
                out[url] = {"type": "pdf", "text": text}
                fetched += 1
        else:
            html = r.text
            text = extract_text_from_html(html)
            if text:
                out[url] = {"type": "html", "text": text}
                fetched += 1

            if depth < max_depth:
                # первичная фильтрация по домену делается в extract_links
                html_links, pdf_links = extract_links(html, url, allowed_domains)
                # приоритет PDF; дополнительно фильтруем по allowed_prefixes
                next_urls = [u for u in (pdf_links + html_links) if _in_allowed_prefix(u)]
                for nxt in next_urls[:40]:  # лёгкое ограничение ветвления
                    if nxt not in seen:
                        queue.append((nxt, depth + 1))

        if on_progress:
            on_progress(f"OK {url}", fetched, max_pages)
        time.sleep(CRAWL_DELAY_SEC)

    return out


# ---------- Индексация и QA ----------
def split_docs(items: Dict[str, Dict]) -> List[Document]:
    docs: List[Document] = []
    for url, meta in items.items():
        t = meta.get("text", "")
        if not t: continue
        docs.append(Document(page_content=t, metadata={"source": url, "type": meta.get("type", "html")}))
    chunks = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150).split_documents(docs)
    # ==== NEW: стабильные chunk_id ====
    for i, d in enumerate(chunks):
        d.metadata["chunk_id"] = f"{d.metadata.get('source','')}\u241f{i}"
    return chunks

def build_vectorstore(docs: List[Document]) -> FAISS:
    embeddings = OllamaEmbeddings(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL)
    return FAISS.from_documents(docs, embeddings)

# ==== NEW: BM25 индекс ====
def build_bm25(docs: List[Document]) -> BM25Okapi:
    corpus = [tokenize(d.page_content) for d in docs]
    return BM25Okapi(corpus)

def get_llm() -> ChatOllama:
    return ChatOllama(model=DEFAULT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.0)

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Отвечай строго по приведённому контексту. Если ответа нет в контексте, скажи: «Не найдено в материалах»."),
    ("human", "Контекст:\n{context}\n\nВопрос: {question}")
])

# ==== NEW: Гибридный ретривер (FAISS MMR + BM25 + RRF) ====
class HybridRetriever:
    def __init__(self, faiss_vs: FAISS, bm25: BM25Okapi, docs: List[Document], k_dense: int = 12, k_sparse: int = 30, out_k: int = 6):
        self.vs = faiss_vs
        self.bm25 = bm25
        self.docs = docs
        self.doc_by_id = {d.metadata["chunk_id"]: d for d in docs}
        self.k_dense = k_dense
        self.k_sparse = k_sparse
        self.out_k = out_k
        # MMR снижает дубликаты
        self.faiss_retr = self.vs.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k_dense, "fetch_k": max(50, k_dense * 4), "lambda_mult": 0.5}
        )

    def _dense_ids(self, q: str) -> List[str]:
        return [d.metadata["chunk_id"] for d in self.faiss_retr.get_relevant_documents(q)]

    def _sparse_ids(self, q: str) -> List[str]:
        toks = tokenize(q)
        scores = self.bm25.get_scores(toks)
        idxs = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: self.k_sparse]
        return [self.docs[i].metadata["chunk_id"] for i in idxs]

    def _rrf(self, dense_ids: List[str], sparse_ids: List[str], rrf_k: int = 60) -> List[Document]:
        ranks: Dict[str, float] = {}
        for rank, cid in enumerate(dense_ids, start=1):
            ranks[cid] = ranks.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        for rank, cid in enumerate(sparse_ids, start=1):
            ranks[cid] = ranks.get(cid, 0.0) + 1.0 / (rrf_k + rank)
        # boost PDF
        for cid in list(ranks.keys()):
            src = self.doc_by_id[cid].metadata.get("source", "")
            if src.lower().endswith(".pdf"):
                ranks[cid] *= 1.05
        ordered = sorted(ranks.items(), key=lambda kv: kv[1], reverse=True)
        out_ids = [cid for cid, _ in ordered[: self.out_k]]
        return [self.doc_by_id[cid] for cid in out_ids]

    def get_relevant_documents(self, query: str) -> List[Document]:
        d_ids = self._dense_ids(query)
        s_ids = self._sparse_ids(query)
        return self._rrf(d_ids, s_ids)

def answer_question(query: str, retriever):
    docs = retriever.get_relevant_documents(query)
    if not docs:
        return "Не найдено в материалах.", []
    top = docs[:3]
    ctx = "\n\n---\n\n".join(d.page_content[:1500] for d in top)
    out = get_llm().invoke(RAG_PROMPT.format_messages(context=ctx, question=query)).content.strip()
    sources = list({d.metadata.get("source") for d in top if d.metadata.get("source")})
    return (out or "Не найдено в материалах."), sources

# ---------- UI ----------
st.set_page_config(page_title="RAG по ссылкам (ITMO)", page_icon="🔎")

# Sidebar: ссылки, прогресс, управление
with st.sidebar:
    st.header("Индексация")
    seeds_state_default = "\n".join(DEFAULT_SEEDS)
    seeds_input = st.text_area("Ссылки (по одной на строке):", value=seeds_state_default, height=120)
    prog_bar = st.progress(0)
    status_box = st.empty()
    meta_box = st.empty()
    col_a, col_b = st.columns(2)
    with col_a:
        btn_rebuild = st.button("Пересобрать", type="primary")
    with col_b:
        btn_clear = st.button("Очистить")
    st.caption("Чат доступен только после завершения индексации.")

# State
if "retriever" not in st.session_state: st.session_state.retriever = None
if "stats" not in st.session_state: st.session_state.stats = {}
if "indexing" not in st.session_state: st.session_state.indexing = False

def build_index_from_ui():
    seeds = [s.strip() for s in (seeds_input or "").splitlines() if s.strip()]
    if not seeds:
        status_box.error("Добавьте ссылки.")
        return
    st.session_state.indexing = True
    prog_bar.progress(0)
    status_box.info("Старт индексации…")

    def on_progress(msg: str, fetched: int, max_pages: int):
        p = min(fetched / max_pages, 1.0) * 0.8
        prog_bar.progress(int(p * 100))
        status_box.write(msg)

    pages = crawl(seeds, max_pages=MAX_PAGES, max_depth=MAX_DEPTH, on_progress=on_progress)
    if not pages:
        status_box.error("Ничего не распарсили.")
        st.session_state.indexing = False
        return

    status_box.info("Разбиение на фрагменты…")
    docs = split_docs(pages)
    prog_bar.progress(90)

    status_box.info("Строю FAISS (dense)…")
    vs = build_vectorstore(docs)
    status_box.info("Строю BM25 (sparse)…")
    bm25 = build_bm25(docs)

    # ==== NEW: гибридный ретривер ====
    retriever = HybridRetriever(vs, bm25, docs, k_dense=12, k_sparse=30, out_k=6)
    st.session_state.retriever = retriever
    st.session_state.stats = {"chunks": len(docs), "sources": list({d.metadata["source"] for d in docs})}

    prog_bar.progress(100)
    meta_box.success(f"Готово: чанков {len(docs)}, источников {len(st.session_state.stats['sources'])}.")
    status_box.success("Индексация завершена.")
    st.session_state.indexing = False

# Автоиндекс при первом запуске
if st.session_state.retriever is None and not st.session_state.indexing:
    build_index_from_ui()

# Кнопки
if btn_clear:
    st.session_state.retriever = None
    st.session_state.stats = {}
    st.session_state.indexing = False
    st.session_state.messages = []
    prog_bar.progress(0)
    status_box.info("Индекс очищен. Соберите заново.")

if btn_rebuild and not st.session_state.indexing:
    st.session_state.messages = []  
    build_index_from_ui()

# Main: чат с историей в рамках сессии (сбрасывается при перезагрузке)
st.title("🔎 Чат по материалам")

# Инициализация хранилища сообщений ТОЛЬКО на время сессии
if "messages" not in st.session_state:
    st.session_state.messages = []  # пусто при каждом перезапуске страницы

# Блокировка до завершения индексации
if st.session_state.indexing or st.session_state.retriever is None:
    st.warning("Чат недоступен до завершения индексации.")
    # Можно показать прогресс/подсказку — но вход отключён
else:
    # Рендер истории текущей сессии
    for msg in st.session_state.messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role):
            st.markdown(msg.get("content", ""))
            # Показать скрытое мышление (если есть)
            if role == "assistant" and msg.get("think"):
                with st.expander("Промежуточные рассуждения модели"):
                    st.code(msg["think"])
            # Показать источники (если есть)
            if role == "assistant" and msg.get("sources"):
                st.caption("Источники:")
                for s in msg["sources"]:
                    st.write(f"- {s}")

    # Ввод сообщения
    user_q = st.chat_input("Напишите вопрос…")
    if user_q:
        # 1) показать пользовательское сообщение
        st.session_state.messages.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        # 2) ответ ассистента
        with st.chat_message("assistant"):
            with st.spinner("Отвечаю по контексту…"):
                ans, srcs = answer_question(user_q, st.session_state.retriever)
                main_text, think_text = split_think(ans)
                st.markdown(main_text or "Не найдено в материалах.")
                if think_text:
                    with st.expander("Промежуточные рассуждения модели"):
                        st.code(think_text)
                if srcs:
                    st.caption("Источники:")
                    for s in srcs:
                        st.write(f"- {s}")

        # 3) сохранить ответ ассистента в историю сессии
        st.session_state.messages.append({
            "role": "assistant",
            "content": main_text or "Не найдено в материалах.",
            "think": think_text,
            "sources": srcs,
        })

